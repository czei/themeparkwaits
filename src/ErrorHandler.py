import os
import traceback

class ErrorHandler:
    @staticmethod
    def filter_non_ascii(text):
        """Filter out non-ASCII characters from a string"""
        if text is None:
            return ""
        return "".join(c for c in str(text) if ord(c) < 128)
    def __init__(self, file_name):
        self.fileName = file_name
        if self.file_exists(file_name) is False:
            try:
                with open(self.fileName, 'w') as file:
                    file.write('')  # Creates an empty file
            except OSError as e:
                pass

    @staticmethod
    def file_exists(file_name):
        file_exists = True
        try:
            status = os.stat(file_name)
        except OSError:
            file_exists = False
        return file_exists

    def error(self, e, str_description):
        except_str = str_description + ":" + str(e)
        st = traceback.format_exception(e)
        st_str = "stack trace:"
        for line in st:
            st_str = st_str + line

        # Write to filesystem when it is write-enabled
        # Print to screen with read-only
        try:
            # Filter out non-ASCII characters to prevent UnicodeEncodeError
            filtered_except_str = self.filter_non_ascii(except_str)
            filtered_st_str = self.filter_non_ascii(st_str)
            
            with open(self.fileName, 'a') as file:
                file.write(filtered_except_str + "\n")
                file.write(filtered_st_str + "\n")
        except OSError:
            print(st_str)
            # print("Error writing to log file")

    def debug(self, message):
        print(message)
        self.write_to_file(message)

    def write_to_file(self, message):
        # Write to filesystem when it is write-enabled
        # Print to screen with read-only
        try:
            # Filter out non-ASCII characters to prevent UnicodeEncodeError
            filtered_message = self.filter_non_ascii(message)
            
            with open(self.fileName, 'a') as file:
                file.write(filtered_message + "\n")
        except OSError:
            pass
            # print("Error writing to log file")

    def info(self, message):
        print(message)
        # self.write_to_file(message)