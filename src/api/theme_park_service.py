"""
Service for fetching and managing theme park data.
Copyright 2024 3DUPFitters LLC
"""
import asyncio
import gc
import json

from src.models.theme_park_list import ThemeParkList
from src.models.vacation import Vacation
from scrollkit.utils.error_handler import ErrorHandler

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
                url = "https://api.themeparks.wiki/v1/destinations"
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
                    
                except ValueError as json_error:  # CircuitPython uses ValueError instead of JSONDecodeError
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
                # themeparks.wiki live data endpoint for a single park
                url = f"https://api.themeparks.wiki/v1/entity/{park_id}/live"
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

                except ValueError as json_error:  # CircuitPython uses ValueError instead of JSONDecodeError
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
        Update all selected parks with fresh data

        Returns:
            Number of parks successfully updated
        """
        if not self.park_list or not self.park_list.selected_parks:
            logger.debug("No selected parks to update")
            return 0

        total_parks = len(self.park_list.selected_parks)

        logger.info(f"Starting sequential update of {total_parks} selected parks")

        # Fetch parks one at a time (NOT asyncio.gather). themeparks.wiki's /live
        # payload is ~90 KB/park; fetching all parks concurrently would hold every
        # raw payload in RAM at once (~370 KB for 4 parks). Doing them sequentially
        # and collecting garbage between parks keeps peak memory to a single payload
        # on the constrained device (research D8 / R1). HTTP is synchronous anyway,
        # so this is no slower. _update_single_park swallows its own errors, so a
        # bad park can't abort the batch.
        updated_count = 0
        for park in self.park_list.selected_parks:
            if await self._update_single_park(park):
                updated_count += 1
            gc.collect()

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

