"""
Web server core containing shared business logic for both CircuitPython and development.
This eliminates the duplication between web_server.py and dev_web_server.py.
Copyright 2024 3DUPFitters LLC
"""
import json
from src.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")


class WebServerCore:
    """Core web server logic shared between CircuitPython and development environments."""
    
    def __init__(self, settings_manager, ota_updater=None):
        """
        Initialize the web server core
        
        Args:
            settings_manager: Settings manager instance
            ota_updater: OTA updater instance (optional)
        """
        self.settings_manager = settings_manager
        self.ota_updater = ota_updater
        
    def generate_main_page(self):
        """Generate the main configuration page HTML"""
        # Get current settings
        settings = self.settings_manager.settings
        current_park = settings.get("park_id", "")
        current_show_time = settings.get("show_time", "10")
        current_brightness = settings.get("brightness_scale", "0.5")
        current_scroll_speed = settings.get("scroll_speed", "0.04")
        
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>Theme Park Wait Times Configuration</title>
    <link rel="stylesheet" type="text/css" href="/style.css">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body>
    <div class="container">
        <h1>Theme Park Wait Times</h1>
        <h2>Configuration</h2>
        
        <form method="POST" action="/">
            <div class="form-group">
                <label for="park_id">Theme Park:</label>
                <select name="park_id" id="park_id" required>
                    <option value="">Select a park...</option>
                    <option value="75ea578a-adc8-4116-a54d-dccb60765ef9" {'selected' if current_park == "75ea578a-adc8-4116-a54d-dccb60765ef9" else ''}>Magic Kingdom</option>
                    <option value="47f90d2c-e191-4239-a466-5892ef59a88b" {'selected' if current_park == "47f90d2c-e191-4239-a466-5892ef59a88b" else ''}>EPCOT</option>
                    <option value="288747d1-8b4f-4a64-867e-ea7c9b27bad8" {'selected' if current_park == "288747d1-8b4f-4a64-867e-ea7c9b27bad8" else ''}>Hollywood Studios</option>
                    <option value="1c84a229-8862-4648-9c71-378ddd2c7693" {'selected' if current_park == "1c84a229-8862-4648-9c71-378ddd2c7693" else ''}>Animal Kingdom</option>
                </select>
            </div>
            
            <div class="form-group">
                <label for="show_time">Display Time (seconds):</label>
                <input type="number" name="show_time" id="show_time" value="{current_show_time}" min="1" max="60" required>
            </div>
            
            <div class="form-group">
                <label for="brightness_scale">Brightness:</label>
                <input type="range" name="brightness_scale" id="brightness_scale" value="{current_brightness}" min="0.1" max="1.0" step="0.1">
                <span id="brightness_value">{current_brightness}</span>
            </div>
            
            <div class="form-group">
                <label for="scroll_speed">Scroll Speed:</label>
                <input type="range" name="scroll_speed" id="scroll_speed" value="{current_scroll_speed}" min="0.01" max="0.1" step="0.01">
                <span id="scroll_value">{current_scroll_speed}</span>
            </div>
            
            <button type="submit" class="btn-primary">Save Settings</button>
        </form>
        
        {self._generate_color_section()}
        {self._generate_ota_section()}
        
        <div class="info-section">
            <h3>Current Settings</h3>
            <pre>{json.dumps(settings, indent=2)}</pre>
        </div>
    </div>
    
    <script>
        // Update brightness display
        document.getElementById('brightness_scale').addEventListener('input', function() {{
            document.getElementById('brightness_value').textContent = this.value;
        }});
        
        // Update scroll speed display
        document.getElementById('scroll_speed').addEventListener('input', function() {{
            document.getElementById('scroll_value').textContent = this.value;
        }});
    </script>
</body>
</html>"""

    def _generate_color_section(self):
        """Generate the color configuration section"""
        settings = self.settings_manager.settings
        
        return f"""
        <div class="color-section">
            <h3>Color Configuration</h3>
            <form method="POST" action="/colors">
                <div class="form-group">
                    <label for="ride_name_color">Ride Name Color:</label>
                    <input type="color" name="ride_name_color" id="ride_name_color" 
                           value="{settings.get('ride_name_color', '#0000FF')}">
                </div>
                
                <div class="form-group">
                    <label for="ride_wait_time_color">Wait Time Color:</label>
                    <input type="color" name="ride_wait_time_color" id="ride_wait_time_color" 
                           value="{settings.get('ride_wait_time_color', '#FDF5E6')}">
                </div>
                
                <div class="form-group">
                    <label for="default_color">Default Text Color:</label>
                    <input type="color" name="default_color" id="default_color" 
                           value="{settings.get('default_color', '#FFFF00')}">
                </div>
                
                <button type="submit" class="btn-secondary">Update Colors</button>
            </form>
        </div>"""

    def _generate_ota_section(self):
        """Generate the OTA update section"""
        if not self.ota_updater:
            return ""
            
        return """
        <div class="ota-section">
            <h3>Over-The-Air Updates</h3>
            <form method="POST" action="/ota">
                <div class="form-group">
                    <label for="github_repo">GitHub Repository:</label>
                    <input type="text" name="github_repo" id="github_repo" 
                           placeholder="username/repository" required>
                </div>
                
                <div class="form-group">
                    <label for="branch">Branch:</label>
                    <input type="text" name="branch" id="branch" value="main" required>
                </div>
                
                <button type="submit" class="btn-warning">Update from GitHub</button>
            </form>
            
            <div class="warning">
                <p><strong>Warning:</strong> OTA updates will restart the device.</p>
            </div>
        </div>"""

    def process_main_form(self, form_data):
        """
        Process main configuration form submission
        
        Args:
            form_data: Dictionary of form data
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Validate required fields
            if not form_data.get("park_id"):
                return False, "Park selection is required"
            
            # Update settings
            self.settings_manager.settings["park_id"] = form_data["park_id"]
            self.settings_manager.settings["show_time"] = form_data.get("show_time", "10")
            self.settings_manager.settings["brightness_scale"] = form_data.get("brightness_scale", "0.5")
            self.settings_manager.settings["scroll_speed"] = form_data.get("scroll_speed", "0.04")
            
            # Save settings
            self.settings_manager.save_settings()
            
            return True, "Settings updated successfully!"
            
        except Exception as e:
            logger.error(e, "Error processing main form")
            return False, f"Error updating settings: {str(e)}"

    def process_color_form(self, form_data):
        """
        Process color configuration form submission
        
        Args:
            form_data: Dictionary of form data
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Update color settings
            if "ride_name_color" in form_data:
                self.settings_manager.settings["ride_name_color"] = form_data["ride_name_color"]
            if "ride_wait_time_color" in form_data:
                self.settings_manager.settings["ride_wait_time_color"] = form_data["ride_wait_time_color"]
            if "default_color" in form_data:
                self.settings_manager.settings["default_color"] = form_data["default_color"]
            
            # Save settings
            self.settings_manager.save_settings()
            
            return True, "Colors updated successfully!"
            
        except Exception as e:
            logger.error(e, "Error processing color form")
            return False, f"Error updating colors: {str(e)}"

    def process_ota_form(self, form_data):
        """
        Process OTA update form submission
        
        Args:
            form_data: Dictionary of form data
            
        Returns:
            Tuple of (success, message)
        """
        if not self.ota_updater:
            return False, "OTA updates not available"
            
        try:
            github_repo = form_data.get("github_repo", "").strip()
            branch = form_data.get("branch", "main").strip()
            
            if not github_repo:
                return False, "GitHub repository is required"
            
            # Trigger OTA update
            success = self.ota_updater.update_from_github(github_repo, branch)
            
            if success:
                return True, "OTA update initiated. Device will restart."
            else:
                return False, "OTA update failed. Check logs for details."
                
        except Exception as e:
            logger.error(e, "Error processing OTA form")
            return False, f"Error starting OTA update: {str(e)}"

    def generate_redirect_response(self, message_type, message):
        """
        Generate a redirect response with status message
        
        Args:
            message_type: 'success' or 'error'
            message: Status message to display
            
        Returns:
            HTML redirect page
        """
        color = "#4CAF50" if message_type == "success" else "#f44336"
        
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>Redirecting...</title>
    <meta http-equiv="refresh" content="3;url=/">
    <link rel="stylesheet" type="text/css" href="/style.css">
</head>
<body>
    <div class="container">
        <div class="message" style="background-color: {color}; color: white; padding: 20px; border-radius: 5px;">
            <h2>{'Success' if message_type == 'success' else 'Error'}</h2>
            <p>{message}</p>
            <p>Redirecting to main page in 3 seconds...</p>
            <a href="/" class="btn-primary">Go back now</a>
        </div>
    </div>
</body>
</html>"""

    def get_static_file_content(self, filename):
        """
        Get static file content
        
        Args:
            filename: Name of the static file
            
        Returns:
            Tuple of (content, content_type) or (None, None) if not found
        """
        try:
            if filename == "style.css":
                return self._get_css_content(), "text/css"
            elif filename in ["gear.jpg", "gear.png"]:
                # Try to read from src/www first, then fall back to src/images
                for path in [f"src/www/{filename}", f"src/images/{filename}"]:
                    try:
                        with open(path, "rb") as f:
                            content_type = "image/jpeg" if filename.endswith(".jpg") else "image/png"
                            return f.read(), content_type
                    except:
                        continue
            
            return None, None
            
        except Exception as e:
            logger.error(e, f"Error serving static file: {filename}")
            return None, None

    def _get_css_content(self):
        """Get CSS content for styling"""
        return """
body {
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 20px;
    background-color: #f5f5f5;
}

.container {
    max-width: 800px;
    margin: 0 auto;
    background-color: white;
    padding: 30px;
    border-radius: 10px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

h1 {
    color: #333;
    text-align: center;
    margin-bottom: 30px;
}

h2, h3 {
    color: #555;
    border-bottom: 2px solid #eee;
    padding-bottom: 10px;
}

.form-group {
    margin-bottom: 20px;
}

label {
    display: block;
    margin-bottom: 5px;
    font-weight: bold;
    color: #333;
}

input[type="text"],
input[type="number"],
input[type="color"],
select {
    width: 100%;
    padding: 10px;
    border: 1px solid #ddd;
    border-radius: 5px;
    font-size: 16px;
    box-sizing: border-box;
}

input[type="range"] {
    width: 80%;
    margin-right: 10px;
}

.btn-primary,
.btn-secondary,
.btn-warning {
    background-color: #007bff;
    color: white;
    padding: 12px 24px;
    border: none;
    border-radius: 5px;
    cursor: pointer;
    font-size: 16px;
    text-decoration: none;
    display: inline-block;
    margin: 5px;
}

.btn-secondary {
    background-color: #6c757d;
}

.btn-warning {
    background-color: #ffc107;
    color: #000;
}

.btn-primary:hover {
    background-color: #0056b3;
}

.btn-secondary:hover {
    background-color: #545b62;
}

.btn-warning:hover {
    background-color: #e0a800;
}

.color-section,
.ota-section,
.info-section {
    margin-top: 30px;
    padding: 20px;
    background-color: #f8f9fa;
    border-radius: 5px;
}

.warning {
    background-color: #fff3cd;
    border: 1px solid #ffeaa7;
    color: #856404;
    padding: 15px;
    border-radius: 5px;
    margin-top: 15px;
}

pre {
    background-color: #f4f4f4;
    padding: 15px;
    border-radius: 5px;
    overflow-x: auto;
    font-size: 14px;
}

.message {
    text-align: center;
    margin: 20px 0;
}

@media (max-width: 600px) {
    .container {
        padding: 15px;
    }
    
    input[type="range"] {
        width: 70%;
    }
}
"""