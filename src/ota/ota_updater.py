import os
import gc
import time
from src.utils.error_handler import ErrorHandler

# Initialize logger
logger = ErrorHandler("error_log")

class OTAUpdater:
    """
    A class to update your MicroController with the latest version from a GitHub tagged release,
    optimized for low power usage.
    """

    def __init__(self, http_client_param, github_repo, github_src_dir='', module='', main_dir='main', new_version_dir='next', secrets_file=None, headers={}, use_prerelease=False):
        self.headers = headers
        self.http_client = http_client_param
        self.github_repo = github_repo.rstrip('/').replace('https://github.com/', '')
        self.github_src_dir = '' if len(github_src_dir) < 1 else github_src_dir.rstrip('/') + '/'
        self.module = module.rstrip('/')
        self.main_dir = main_dir
        self.new_version_dir = new_version_dir
        self.secrets_file = secrets_file
        self.use_prerelease = use_prerelease  # Support pre-releases for testing
        self.update_progress_callback = None  # Callback for update progress

    def __del__(self):
        self.http_client = None

    def check_for_update_to_install_during_next_reboot(self):
        """Function which will check the GitHub repo if there is a newer version available.
        
        This method expects an active internet connection and will compare the current 
        version with the latest version available on GitHub.
        If a newer version is available, the file 'next/.version' will be created 
        and you need to call machine.reset(). A reset is needed as the installation process 
        takes up a lot of memory (mostly due to the http stack)

        Returns
        -------
            bool: true if a new version is available, false otherwise
        """

        (current_version, latest_version) = self.check_for_new_version()
        if latest_version > current_version:
            logger.info('New version available, will download and install on next reboot')
            self._create_new_version_file(latest_version)
            return True
        else:
            logger.info(f'No update available. Current: {current_version}, Latest: {latest_version}')

        return False

    def update_available_at_boot(self):
        # Handle empty module path (default to current directory)
        module_path = self.module if self.module else '.'
        try:
            module_contents = os.listdir(module_path)
            if self.new_version_dir not in module_contents:
                return False
            
            new_version_path = self.modulepath(self.new_version_dir)
            new_version_contents = os.listdir(new_version_path)
            is_available = '.version' in new_version_contents
            return is_available
        except (OSError, FileNotFoundError):
            # Directory doesn't exist or can't be accessed
            return False

    def install_update_if_available_after_boot(self, ssid, password):
        """This method will install the latest version if out-of-date after boot.
        
        This method, which should be called first thing after booting, will check if the 
        next/.version' file exists. 

        - If yes, it initializes the WIFI connection, downloads the latest version and installs it
        - If no, the WIFI connection is not initialized as no new known version is available
        """

        # Handle empty module path (default to current directory)
        module_path = self.module if self.module else '.'
        try:
            if self.new_version_dir in os.listdir(module_path):
                if '.version' in os.listdir(self.modulepath(self.new_version_dir)):
                    latest_version = self.get_version(self.modulepath(self.new_version_dir), '../.version')
                    logger.info(f'New update found: {latest_version}')
                    OTAUpdater._using_network(ssid, password)
                    self.install_update_if_available()
                    return True
        except (OSError, FileNotFoundError):
            # Directory doesn't exist or can't be accessed
            pass
            
        logger.info('No new updates found...')
        return False

    def install_update_if_available(self):
        """This method will immediately install the latest version if out-of-date.
        
        This method expects an active internet connection and allows you to decide yourself
        if you want to install the latest version. It is necessary to run it directly after boot 
        (for memory reasons) and you need to restart the microcontroller if a new version is found.

        Returns
        -------
            bool: true if a new version is available, false otherwise
        """

        (current_version, latest_version) = self.check_for_new_version()
        if latest_version > current_version:
            self._create_new_version_file(latest_version)
            self._download_new_version(latest_version)
            self._copy_secrets_file()
            self._delete_old_version()
            self._install_new_version()
            return True
        
        return False


    @staticmethod
    def _using_network(ssid, password):
        # In current codebase, WiFi should already be connected by WiFiManager
        # This method is kept for compatibility but may not be needed
        logger.info("WiFi connection should already be established by WiFiManager")

    def check_for_new_version(self):
        current_version = self.get_version(self.modulepath(self.main_dir))
        latest_version = self.get_latest_version()

        logger.info('Checking version... ')
        logger.info(f'\tCurrent version: {current_version}')
        logger.info(f'\tLatest version: {latest_version}')
        return (current_version, latest_version)

    def _create_new_version_file(self, latest_version):
        self.mkdir(self.modulepath(self.new_version_dir))
        with open(self.modulepath(self.new_version_dir + '/.version'), 'w') as versionfile:
            versionfile.write(latest_version)
            versionfile.close()

    def get_version(self, directory, version_file_name='.version'):
        try:
            if version_file_name in os.listdir(directory):
                with open(directory + '/' + version_file_name) as f:
                    version = f.read().strip()
                    return version
        except (OSError, FileNotFoundError):
            # Directory doesn't exist or can't be accessed
            pass
        return '0.0'

    def get_latest_version(self):
        if self.use_prerelease:
            # Get all releases including pre-releases for testing
            url = "https://api.github.com/repos/{}/releases".format(self.github_repo)
            logger.info(f"Checking all releases (including pre-releases) at: {url}")
            
            try:
                response = self.http_client.get_sync(url, headers=self.headers)
                releases = response.json()
                response.close()
                
                if releases and len(releases) > 0:
                    # Get the first release (most recent)
                    version = releases[0]['tag_name']
                    is_prerelease = releases[0].get('prerelease', False)
                    logger.info(f"Found {'pre-release' if is_prerelease else 'release'}: {version}")
                    return version
                else:
                    raise ValueError("No releases found")
                    
            except Exception as e:
                logger.error(e, "Error fetching releases")
                raise ValueError(f"Error fetching releases: {e}")
        else:
            # Get only the latest stable release
            url = "https://api.github.com/repos/{}/releases/latest".format(self.github_repo)
            logger.info(f"Checking latest stable release at: {url}")
            
            try:
                response = self.http_client.get_sync(url, headers=self.headers)
                gh_json = response.json()
                response.close()
                
                version = gh_json['tag_name']
                logger.info(f"Found latest stable release: {version}")
                return version
                
            except KeyError as e:
                raise ValueError(
                    "Release not found. Please ensure release is marked as 'latest', not pre-release"
                )
            except Exception as e:
                logger.error(e, "Error fetching latest release")
                raise ValueError(f"Error fetching latest release: {e}")

    def _download_new_version(self, version):
        logger.info(f'Downloading version {version}')
        if self.update_progress_callback:
            self.update_progress_callback("Starting download...")
        
        self._download_all_files(version)
        
        logger.info(f'Version {version} downloaded to {self.modulepath(self.new_version_dir)}')
        if self.update_progress_callback:
            self.update_progress_callback("Download complete!")

    def _download_all_files(self, version, sub_dir=''):
        url = 'https://api.github.com/repos/{}/contents{}{}{}?ref=refs/tags/{}'.format(
            self.github_repo, self.github_src_dir, self.main_dir, sub_dir, version
        )
        logger.debug(f"Fetching file list from {url}")
        gc.collect()
        
        try:
            response = self.http_client.get_sync(url, headers=self.headers)
            file_list_json = response.json()
            response.close()
        except Exception as e:
            logger.error(e, f"Error fetching file list from {url}")
            raise
        
        # Count total files for progress
        file_count = sum(1 for f in file_list_json if f['type'] == 'file')
        files_downloaded = 0
        
        for file in file_list_json:
            path = self.modulepath(self.new_version_dir + '/' + file['path'].replace(self.main_dir + '/', '').replace(self.github_src_dir, ''))
            
            if file['type'] == 'file':
                gitPath = file['path']
                
                # Check if file needs to be downloaded (compare with existing if possible)
                needs_download = True
                existing_path = self.modulepath(self.main_dir + '/' + file['path'].replace(self.main_dir + '/', '').replace(self.github_src_dir, ''))
                
                # For now, always download. In future, could compare SHA hashes
                if needs_download:
                    logger.info(f'Downloading: {gitPath}')
                    if self.update_progress_callback:
                        files_downloaded += 1
                        progress_msg = f"Downloading {files_downloaded}/{file_count}: {os.path.basename(gitPath)}"
                        self.update_progress_callback(progress_msg)
                    
                    self._download_file(version, gitPath, path)
                    
            elif file['type'] == 'dir':
                logger.debug(f'Creating directory: {path}')
                self.mkdir(path)
                self._download_all_files(version, sub_dir + '/' + file['name'])
                
            # Aggressive garbage collection to manage memory
            gc.collect()

    def _download_file(self, version, gitPath, path):
        try:
            url = 'https://raw.githubusercontent.com/{}/{}/{}'.format(self.github_repo, version, gitPath)
            response = self.http_client.get_sync(url, headers=self.headers)
            
            # Write file in chunks to manage memory
            with open(path, "wb") as file:
                # If response has content attribute, use it
                if hasattr(response, 'content'):
                    file.write(response.content)
                else:
                    # Otherwise read in chunks
                    chunk_size = 512
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        file.write(chunk)
                        gc.collect()
            
            response.close()
            logger.debug(f"Downloaded {gitPath} successfully")
            
        except Exception as e:
            logger.error(e, f"Error downloading file {gitPath}")
            # Clean up partial file
            try:
                os.remove(path)
            except:
                pass
            raise

    def _copy_secrets_file(self):
        """Copy secrets.py and settings.json to preserve user configuration"""
        files_to_preserve = ['secrets.py', 'settings.json']
        
        for filename in files_to_preserve:
            fromPath = self.modulepath(self.main_dir + '/' + filename)
            toPath = self.modulepath(self.new_version_dir + '/' + filename)
            
            # Check if file exists before copying
            if self._exists_file(fromPath):
                logger.info(f'Preserving {filename}')
                try:
                    self._copy_file(fromPath, toPath)
                    logger.debug(f'Copied {filename} successfully')
                except Exception as e:
                    logger.error(e, f'Error copying {filename}')
                    # Continue with update even if settings can't be copied
            else:
                logger.debug(f'{filename} not found, skipping')

    def _delete_old_version(self):
        logger.info('Deleting old version at {} ...'.format(self.modulepath(self.main_dir)))
        self._rmtree(self.modulepath(self.main_dir))
        logger.info('Deleted old version at {} ...'.format(self.modulepath(self.main_dir)))

    def _install_new_version(self):
        logger.info('Installing new version at {} ...'.format(self.modulepath(self.main_dir)))
        if self._os_supports_rename():
            logger.info(f"Renaming {self.new_version_dir} to {self.modulepath(self.main_dir)}")
            os.rename(self.modulepath(self.new_version_dir), self.modulepath(self.main_dir))
        else:
            logger.info(f"Copying individual files from {self.new_version_dir} to {self.modulepath(self.main_dir)}")
            self._copy_directory(self.modulepath(self.new_version_dir), self.modulepath(self.main_dir))
            self._rmtree(self.modulepath(self.new_version_dir))
        logger.info('Update installed, please reboot now')

    def _rmtree(self, directory):
        for entry in os.listdir(directory):
            logger.debug(f"Deleting file {directory + '/' + entry}")
            stat = os.stat(directory + '/' + entry)
            is_dir = (stat[0] & 0o170000) == 0o040000
            if is_dir:
                self._rmtree(directory + '/' + entry)
            else:
                os.remove(directory + '/' + entry)
        os.rmdir(directory)

    def _os_supports_rename(self):
        self._mk_dirs('otaUpdater/osRenameTest')
        os.rename('otaUpdater', 'otaUpdated')
        result = len(os.listdir('otaUpdated')) > 0
        self._rmtree('otaUpdated')
        return result

    #
    # Now only works on simple directories with no sub-directories
    #
    def _copy_directory(self, fromPath, toPath):
        if not self._exists_dir(toPath):
            self._mk_dirs(toPath)

        logger.debug(f"Copying directory {fromPath} to {toPath}")
        for entry in os.listdir(fromPath):
            stat = os.stat(fromPath+ '/' + entry)
            is_dir = (stat[0] & 0o170000) == 0o040000
            is_dir = (stat[0] & 0x4000) != 0
            if is_dir:
                logger.debug(f"Recursively copying directory {fromPath}/{entry} to {toPath}/{entry}")
                self._copy_directory(fromPath + '/' + entry, toPath + '/' + entry)
            else:
                logger.debug(f"Copying file {fromPath}/{entry} to {toPath}/{entry}" )
                self._copy_file(fromPath + '/' + entry, toPath + '/' + entry)

    def _copy_file(self, fromPath, toPath):
        with open(fromPath) as fromFile:
            with open(toPath, 'w') as toFile:
                CHUNK_SIZE = 512 # bytes
                data = fromFile.read(CHUNK_SIZE)
                while data:
                    toFile.write(data)
                    data = fromFile.read(CHUNK_SIZE)
            toFile.close()
        fromFile.close()

    def _exists_dir(self, path):
        try:
            os.listdir(path)
            return True
        except:
            return False
    
    def _exists_file(self, path):
        """Check if a file exists"""
        try:
            os.stat(path)
            return True
        except:
            return False

    def _mk_dirs(self, path):
        paths = path.split('/')

        pathToCreate = ''
        for x in paths:
            self.mkdir(pathToCreate + x)
            pathToCreate = pathToCreate + x + '/'

    # different micropython versions act differently when directory already exists
    def mkdir(self, path):
        try:
            os.mkdir(path)
        except OSError as exc:
            if exc.args[0] == 17: 
                pass


    def modulepath(self, path):
        return self.module + '/' + path if self.module else path