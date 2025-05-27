"""
Service for fetching and managing theme park data.
Copyright 2024 3DUPFitters LLC
"""
import asyncio
import json

from src.models.theme_park import ThemePark
from src.models.theme_park_list import ThemeParkList
from src.models.vacation import Vacation
from src.config.settings_manager import SettingsManager
from src.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")


class ThemeParkService:
    """
    Service for fetching and managing theme park data
    """
    
    def __init__(self, http_client, settings_manager):
        """
        Initialize the theme park service
        
        Args:
            http_client: The HTTP client to use for requests
            settings_manager: The settings manager
        """
        self.http_client = http_client
        self.settings_manager = settings_manager
        self.park_list = None
        self.vacation = Vacation()
        self.update_needed = False  # Flag to indicate if an update should be forced
        
    async def initialize(self):
        """Initialize the service by fetching park list and setting clock"""
        # Track initialization steps for better error reporting
        steps_completed = []

        try:
            # Step 1: Load vacation data from settings
            try:
                self.vacation.load_settings(self.settings_manager)
                steps_completed.append("vacation_loaded")
                logger.info("Vacation data loaded from settings")
            except Exception as vacation_error:
                logger.error(vacation_error, "Error loading vacation data")

            # Step 2: Fetch park list from URL (skipping the check since we need data first)
            # Note: This code was trying to create an empty ThemeParkList without data
            # Let the fetch_park_list code below handle the actual creation

            # Step 3: Fetch the park list
            for attempt in range(3):  # Multiple attempts for park list
                try:
                    logger.info(f"Attempting to fetch park list (attempt {attempt+1}/3)")
                    await self.fetch_park_list()
                    if self.park_list and self.park_list.park_list:
                        steps_completed.append("fetch_park_list")
                        logger.info(f"Successfully fetched {len(self.park_list.park_list)} parks on attempt {attempt+1}")
                        break
                    else:
                        logger.error(None, f"Park list fetch attempt {attempt+1} returned empty list")
                        # Small delay before retrying
                        await asyncio.sleep(3)
                except Exception as list_error:
                    logger.error(list_error, f"Error fetching park list on attempt {attempt+1}/3")
                    await asyncio.sleep(3)
            
            # Create empty park list if all attempts failed
            if "fetch_park_list" not in steps_completed:
                logger.info("Creating empty park list as fallback after failed attempts")
                self.park_list = ThemeParkList([])
            
            # Step 3: Load settings (even for empty park list)
            if self.park_list:
                self.park_list.load_settings(self.settings_manager)
                steps_completed.append("load_park_settings")
                
            # Step 4: Load vacation settings
            self.vacation.load_settings(self.settings_manager)
            steps_completed.append("load_vacation_settings")
            
            # Log initialization success/partial success
            if len(steps_completed) >= 3:  # Clock setting might fail but that's ok
                logger.info(f"Theme park service initialized. Steps completed: {', '.join(steps_completed)}")
            else:
                logger.error(None, f"Theme park service partially initialized. Steps completed: {', '.join(steps_completed)}")
            
        except Exception as e:
            logger.error(e, f"Error initializing theme park service. Steps completed: {', '.join(steps_completed)}")
            
            # Create park list if it doesn't exist yet (failsafe)
            if self.park_list is None:
                self.park_list = ThemeParkList([])
                logger.info("Created empty park list as failsafe after initialization error")
            
    async def fetch_park_list(self):
        """
        Fetch the list of theme parks
        
        Returns:
            A ThemeParkList object, or None if fetch failed
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                url = "https://queue-times.com/parks.json"
                logger.info(f"Fetching park list from {url} (attempt {retry_count + 1}/{max_retries})")
                
                response = await self.http_client.get(url)
                
                if not response or not hasattr(response, 'text'):
                    logger.error(None, f"Invalid response when fetching park list (attempt {retry_count + 1})")
                    retry_count += 1
                    await asyncio.sleep(1)
                    continue
                
                # Try to parse JSON
                try:
                    data = json.loads(response.text)
                    if not data:
                        logger.error(None, f"Empty JSON data from park list API (attempt {retry_count + 1})")
                        retry_count += 1
                        await asyncio.sleep(1)
                        continue
                    
                    # Create park list
                    self.park_list = ThemeParkList(data)
                    
                    # Verify park list has parks
                    if not self.park_list.park_list:
                        logger.error(None, f"Park list created but no parks were found (attempt {retry_count + 1})")
                        retry_count += 1
                        await asyncio.sleep(1)
                        continue
                    
                    logger.info(f"Successfully fetched {len(self.park_list.park_list)} parks")
                    return self.park_list
                    
                except json.JSONDecodeError as json_error:
                    logger.error(json_error, f"JSON decode error for park list (attempt {retry_count + 1})")
                    retry_count += 1
                    await asyncio.sleep(1)
                    continue
                
            except Exception as e:
                logger.error(e, f"Error fetching park list (attempt {retry_count + 1})")
                retry_count += 1
                await asyncio.sleep(1)
        
        # All retries failed
        logger.error(None, f"Failed to fetch park list after {max_retries} attempts")
        
        # Create empty park list as fallback
        self.park_list = ThemeParkList([])
        return self.park_list
            
    async def fetch_park_data(self, park_id):
        """
        Fetch data for a specific park (optimized for speed)

        Args:
            park_id: The ID of the park

        Returns:
            Park data as a dictionary, or None if fetch failed
        """
        max_retries = 2  # Reduced from 3 to 2
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Use the correct URL format for fetching park ride data
                url = f"https://queue-times.com/parks/{park_id}/queue_times.json"
                logger.info(f"Fetching data for park ID {park_id} from {url} (attempt {retry_count + 1}/{max_retries})")

                response = await self.http_client.get(url)

                if not response or not hasattr(response, 'text'):
                    logger.error(None, f"Invalid response when fetching park data (attempt {retry_count + 1})")
                    retry_count += 1
                    if retry_count < max_retries:
                        await asyncio.sleep(0.5)  # Reduced from 1s to 0.5s
                    continue

                # Try to parse JSON
                try:
                    data = json.loads(response.text)
                    if not data:
                        logger.error(None, f"Empty JSON data from park API (attempt {retry_count + 1})")
                        retry_count += 1
                        if retry_count < max_retries:
                            await asyncio.sleep(0.5)  # Reduced from 1s to 0.5s
                        continue

                    logger.info(f"Successfully fetched data for park ID {park_id}")
                    return data

                except json.JSONDecodeError as json_error:
                    logger.error(json_error, f"JSON decode error for park data (attempt {retry_count + 1})")
                    retry_count += 1
                    if retry_count < max_retries:
                        await asyncio.sleep(0.5)  # Reduced from 1s to 0.5s
                    continue

            except Exception as e:
                logger.error(e, f"Error fetching park data for park ID {park_id} (attempt {retry_count + 1})")
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(0.5)  # Reduced from 1s to 0.5s

        # All retries failed
        logger.error(None, f"Failed to fetch park data for park ID {park_id} after {max_retries} attempts")
        return None
            
    async def update_current_park(self):
        """
        Update the currently selected park with fresh data

        Returns:
            True if successful, False otherwise
        """
        if not self.park_list or not self.park_list.current_park.is_valid():
            logger.debug("No valid current park to update")
            return False

        try:
            park_data = await self.fetch_park_data(self.park_list.current_park.id)
            if park_data:
                self.park_list.current_park.update(park_data)
                return True
            return False

        except Exception as e:
            logger.error(e, "Error updating current park")
            return False
            
    async def update_selected_parks(self):
        """
        Update all selected parks with fresh data (parallel fetching for speed)
        
        Returns:
            Number of parks successfully updated
        """
        if not self.park_list or not self.park_list.selected_parks:
            logger.debug("No selected parks to update")
            return 0
            
        total_parks = len(self.park_list.selected_parks)
        
        logger.info(f"Starting parallel update of {total_parks} selected parks")
        
        # Create tasks for all parks to fetch in parallel
        tasks = []
        for park in self.park_list.selected_parks:
            task = asyncio.create_task(self._update_single_park(park))
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful updates
        updated_count = sum(1 for result in results if result is True)
        
        logger.info(f"Updated {updated_count}/{total_parks} selected parks")
        return updated_count
    
    async def _update_single_park(self, park):
        """
        Update a single park with error handling
        
        Args:
            park: The park to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.debug(f"Updating park: {park.name} (ID: {park.id})")
            park_data = await self.fetch_park_data(park.id)
            if park_data:
                park.update(park_data)
                logger.debug(f"Successfully updated park: {park.name}")
                return True
            else:
                logger.error(None, f"Failed to fetch data for park: {park.name}")
                return False
        except Exception as e:
            logger.error(e, f"Error updating park: {park.name}")
            return False

    async def get_ride_wait_times(self, park_id=None, ride_name=None):
        """
        Get wait times for rides in a specific park or a specific ride

        Args:
            park_id: Optional ID of the park (defaults to current park if None)
            ride_name: Optional name of a specific ride to get wait time for

        Returns:
            Dictionary of ride names to wait times, or single wait time if ride_name provided
        """
        try:
            # Use current park if no park_id provided
            if park_id is None and self.park_list and self.park_list.current_park.is_valid():
                park_id = self.park_list.current_park.id

            if not park_id:
                logger.error(None, "No valid park ID for getting ride wait times")
                return None

            # Fetch park data
            park_data = await self.fetch_park_data(park_id)
            if not park_data:
                logger.error(None, f"Failed to fetch park data for wait times (park ID: {park_id})")
                return None

            # Create temporary park object to parse the data
            temp_park = ThemePark(park_data)

            # If looking for a specific ride
            if ride_name:
                for ride in temp_park.rides:
                    if ride.name.lower() == ride_name.lower():
                        return {
                            "name": ride.name,
                            "wait_time": ride.wait_time,
                            "is_open": ride.open_flag
                        }
                logger.error(None, f"Ride '{ride_name}' not found in park {park_id}")
                return None

            # Return all rides
            wait_times = {}
            for ride in temp_park.rides:
                wait_times[ride.name] = {
                    "wait_time": ride.wait_time,
                    "is_open": ride.open_flag
                }

            return wait_times

        except Exception as e:
            logger.error(e, f"Error getting ride wait times for park {park_id}")
            return None
            
    def save_settings(self):
        """Save all settings"""
        if self.park_list:
            self.park_list.store_settings(self.settings_manager)
        
        self.vacation.store_settings(self.settings_manager)
        self.settings_manager.save_settings()
        
    def parse_query_params(self, params):
        """
        Parse query parameters for park and vacation settings

        Args:
            params: The query parameter string
        """
        if not self.park_list:
            return

        # Check for park parameters
        if "park-id=" in params:
            self.park_list.parse(params)

        # Check for vacation parameters
        if "Name=" in params:
            self.vacation.parse(params)

        # Save the settings
        self.save_settings()

    async def get_available_parks(self):
        """
        Get a list of all available theme parks

        Returns:
            List of dictionaries with park information (id, name, company)
        """
        try:
            # Make sure park list is initialized
            if not self.park_list or not self.park_list.park_list:
                await self.fetch_park_list()

            if not self.park_list or not self.park_list.park_list:
                logger.error(None, "Failed to fetch park list for available parks")
                return []

            # Convert park list to a simple dictionary format
            parks = []
            for park in self.park_list.park_list:
                parks.append({
                    "id": park.id,
                    "name": park.name,
                    "latitude": park.latitude,
                    "longitude": park.longitude
                })

            return parks

        except Exception as e:
            logger.error(e, "Error getting available parks")
            return []

    async def search_parks(self, query):
        """
        Search for parks matching a query string

        Args:
            query: Search term (park name)

        Returns:
            List of matching parks
        """
        try:
            parks = await self.get_available_parks()
            if not query:
                return parks

            # Filter parks by name
            query = query.lower()
            matching_parks = [
                park for park in parks
                if query in park["name"].lower()
            ]

            return matching_parks

        except Exception as e:
            logger.error(e, f"Error searching parks for '{query}'")
            return []
            
    def get_available_rides(self, park_id=None):
        """
        Get a list of all available rides for the current park or a specific park
        
        Args:
            park_id: Optional park ID to get rides for (defaults to current park)
        
        Returns:
            List of dictionaries with ride information (name, wait_time, is_open)
        """
        rides = []
        try:
            if park_id:
                # Get park by ID
                park = self.park_list.get_park_by_id(park_id) if self.park_list else None
                if not park:
                    logger.error(None, f"Park with ID {park_id} not found")
                    return []
            else:
                # Use current park
                park = self.park_list.current_park if self.park_list else None
                if not park or not park.is_valid():
                    logger.error(None, "No valid current park")
                    return []
                    
            # If park has no rides, it might be a newly selected park
            # that hasn't had its data fetched yet
            if not park.rides:
                logger.info(f"No rides found for park {park.name}, park may need data update")
                return []
                
            for ride in park.rides:
                rides.append({
                    "name": ride.name,
                    "wait_time": ride.wait_time,
                    "is_open": ride.open_flag
                })
        except Exception as e:
            logger.error(e, "Error getting available rides")
        return rides
    
    async def get_rides_for_park_async(self, park_id):
        """
        Fetch ride data for a specific park asynchronously
        
        Args:
            park_id: The ID of the park to fetch rides for
            
        Returns:
            List of ride dictionaries or empty list if failed
        """
        try:
            # Use the correct URL format: https://queue-times.com/parks/{id}/queue_times.json
            url = f"https://queue-times.com/parks/{park_id}/queue_times.json"
            logger.info(f"Fetching ride data from {url}")
            
            # Fetch the ride data
            response = await self.http_client.get(url)
            
            if not response or not hasattr(response, 'text'):
                logger.error(None, f"Invalid response when fetching ride data for park ID {park_id}")
                return []
                
            # Parse the JSON response
            try:
                data = json.loads(response.text)
                if not data:
                    logger.error(None, f"Empty JSON data from rides API for park ID {park_id}")
                    return []
                    
                # Create temporary park object to parse the data
                temp_park = ThemePark(data)
                
                rides = []
                for ride in temp_park.rides:
                    rides.append({
                        "name": ride.name,
                        "wait_time": ride.wait_time,
                        "is_open": ride.open_flag
                    })
                
                logger.info(f"Successfully fetched {len(rides)} rides for park ID {park_id}")
                return rides
            except json.JSONDecodeError as json_error:
                logger.error(json_error, f"JSON decode error for ride data (park ID {park_id})")
                return []
                
        except Exception as e:
            logger.error(e, f"Error fetching rides for park ID {park_id}")
            return []