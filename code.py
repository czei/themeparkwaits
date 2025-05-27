"""
ThemeParkAPI - Entry point
Copyright 2024 3DUPFitters LLC
"""
import asyncio
from theme_park_main import main

# Run the main function
try:
    asyncio.run(main())
except (KeyboardInterrupt, Exception) as e:
    # Error will be logged in the main module
    pass