def generate_main_page(self):
    """
    Generate the main HTML page optimized for performance
    
    Returns:
        HTML content for the main page
    """
    # Use list for efficient string building
    parts = []
    
    # Pre-build static header
    parts.extend([
        "<!DOCTYPE html><html><head>",
        "<title>Theme Park Waits</title>",
        '<link rel="stylesheet" href="/style.css">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "</head><body>",
        '<div class="navbar">',
        '<a href="/">Theme Park Wait Times</a>',
        '<div class="gear-icon">',
        '<a href="/settings"><img src="gear.png" alt="Settings"></a>',
        "</div></div>",
        '<div class="main-content">',
        "<h2>Theme Park Selection</h2>"
    ])

    # Cache frequently accessed attributes
    has_theme_park_service = hasattr(self.app, 'theme_park_service')
    theme_park_service = self.app.theme_park_service if has_theme_park_service else None
    has_park_list = theme_park_service and hasattr(theme_park_service, 'park_list')
    park_list = theme_park_service.park_list if has_park_list else None
    settings_manager = self.app.settings_manager if hasattr(self.app, 'settings_manager') else None
    settings = settings_manager.settings if settings_manager else {}

    # Get parks data efficiently
    try:
        response_data = {
            "parks": [],
            "settings": settings,
            "success": True
        }

        parks = []
        if has_park_list and hasattr(park_list, 'park_list'):
            # Build parks list efficiently
            for park in park_list.park_list:
                if hasattr(park, 'id') and hasattr(park, 'name'):
                    parks.append({"id": park.id, "name": park.name})
        
        response_data["parks"] = parks

        # Get current park info if available
        if (has_park_list and 
            hasattr(park_list, 'current_park') and 
            park_list.current_park and 
            hasattr(park_list.current_park, 'is_valid')):
            try:
                if park_list.current_park.is_valid():
                    current_park = park_list.current_park
                    ride_count = len(current_park.rides) if hasattr(current_park, 'rides') else 0
                    response_data["current_park"] = {
                        "id": current_park.id,
                        "name": current_park.name,
                        "ride_count": ride_count
                    }
            except Exception:
                pass

    except Exception as e:
        logger.error(e, "Error getting app data for main page")
        response_data = {"parks": [], "settings": {}, "success": False}

    # Generate form
    if "parks" in response_data:
        parts.append('<form action="/" method="get">')
        
        # Get selected parks efficiently
        selected_park_ids = []
        if has_park_list and hasattr(park_list, 'selected_parks'):
            selected_park_ids = [p.id for p in park_list.selected_parks]
        
        # Park selection section
        parts.extend([
            '<div class="park-selection">',
            '<h3>Select Parks (up to 4)</h3>'
        ])
        
        parks = response_data.get("parks", [])
        
        # Generate park dropdowns efficiently
        for i in range(1, 5):
            parts.extend([
                f'<div class="park-dropdown">',
                f'<label for="park-id-{i}">Park {i}:</label>',
                f'<select name="park-id-{i}" id="park-select-{i}">'
            ])
            
            # Default option
            parts.append(f'<option value="0">Select Park {i}</option>')
            
            if not parks:
                parts.append('<option value="0">No parks available - check connection</option>')
            else:
                # Get current selection
                current_selection = selected_park_ids[i-1] if i <= len(selected_park_ids) else None
                
                # Build options efficiently
                for park in parks:
                    park_id = park.get("id", "")
                    park_name = park.get("name", "Unknown Park")
                    if park_id == current_selection:
                        parts.append(f'<option value="{park_id}" selected>{park_name}</option>')
                    else:
                        parts.append(f'<option value="{park_id}">{park_name}</option>')
            
            parts.extend(['</select>', '</div>'])
        
        parts.append('</div>')  # end park-selection
        
        # Display options section
        parts.extend([
            '<div class="options">',
            '<h3 style="margin-top: 0; margin-bottom: 10px; text-align: left; padding-left: 20px;">Display Options</h3>',
            '<div class="form-group">',
            '<input type="hidden" name="display_mode" value="all_rides">',
            '</div>'
        ])
        
        # Skip options section
        parts.append('<div class="display-options">')
        
        # Skip Closed Rides checkbox
        skip_closed = False
        if has_park_list and hasattr(park_list, 'skip_closed'):
            skip_closed = bool(park_list.skip_closed)
        
        parts.extend([
            '<div class="form-group checkbox-group">',
            f'<input type="checkbox" id="skip_closed" name="skip_closed"{"" if not skip_closed else " checked"}>',
            '<label for="skip_closed">Skip Closed Rides</label>',
            '</div>'
        ])
        
        # Skip Meet & Greets checkbox
        skip_meet = False
        if has_park_list and hasattr(park_list, 'skip_meet'):
            skip_meet = bool(park_list.skip_meet)
        
        parts.extend([
            '<div class="form-group checkbox-group">',
            f'<input type="checkbox" id="skip_meet" name="skip_meet"{"" if not skip_meet else " checked"}>',
            '<label for="skip_meet">Skip Meet & Greets</label>',
            '</div>',
            '</div>',  # end display-options
            '</div>'   # end options
        ])
    else:
        parts.append('<p>No theme parks available.</p>')

    # Vacation date section
    from src.models.vacation import Vacation
    vacation_date = Vacation()
    if settings_manager:
        vacation_date.load_settings(settings_manager)
    
    parts.extend([
        '<h2>Configure Countdown</h2>',
        '<div class="countdown-section">',
        '<p>',
        '<label for="Name">Event:</label>',
        f'<input type="text" name="Name" value="{vacation_date.name}">',
        '</p>',
        '<p>',
        '<label for="Date">Date:</label>',
        '<div class="date-selectors">'
    ])
    
    # Year dropdown - optimized
    parts.append('<select id="Year" name="Year">')
    from adafruit_datetime import datetime
    year_now = datetime.now().year
    vacation_year = vacation_date.year if vacation_date.is_set() else None
    
    # Build year options efficiently
    year_options = []
    for year in range(year_now, 2044):
        if year == vacation_year:
            year_options.append(f'<option value="{year}" selected>{year}</option>')
        else:
            year_options.append(f'<option value="{year}">{year}</option>')
    parts.extend(year_options)
    parts.append('</select>')
    
    # Month dropdown - optimized
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    parts.append('<select id="Month" name="Month">')
    vacation_month = vacation_date.month if vacation_date.is_set() else None
    
    for month in range(1, 13):
        if month == vacation_month:
            parts.append(f'<option value="{month}" selected>{month_names[month-1]}</option>')
        else:
            parts.append(f'<option value="{month}">{month_names[month-1]}</option>')
    parts.append('</select>')
    
    # Day dropdown - optimized
    parts.append('<select id="Day" name="Day">')
    vacation_day = vacation_date.day if vacation_date.is_set() else None
    
    for day in range(1, 32):
        if day == vacation_day:
            parts.append(f'<option value="{day}" selected>{day}</option>')
        else:
            parts.append(f'<option value="{day}">{day}</option>')
    parts.append('</select>')
    
    parts.extend([
        '</div>',  # end date-selectors
        '</p>'
    ])
    
    # Show countdown if vacation is set
    if vacation_date.is_set():
        days_until = vacation_date.get_days_until()
        if days_until > 0:
            parts.extend([
                '<p style="text-align: center; font-weight: bold; margin-top: 10px;">',
                f'Days until {vacation_date.name}: {days_until}',
                '</p>'
            ])
    
    parts.extend([
        '</div>',  # end countdown-section
        '<button type="submit">Update</button>',
        '</form>',
        '</div></body></html>'
    ])
    
    # Join all parts at once
    return ''.join(parts)