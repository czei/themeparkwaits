import os
import traceback

class ErrorHandler:
    def __init__(self, file_name):
        self.fileName = file_name
        if self.file_exists(file_name) is False:
            with open(self.fileName, 'w') as file:
                file.write('')  # Creates an empty file

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
            with open(self.fileName, 'a') as file:
                file.write(except_str + "\n")
                file.write(st_str + "\n")
        except OSError:
            print(st_str)
            print("UnicodeEncodeError")

    def debug(self, message):
        print(message)
        # try:
        #     with open(self.fileName, 'a') as file:
        #         file.write(message + "\n")
        # except OSError:
        #     print(message)

    @staticmethod
    def info(message):
        print(message)