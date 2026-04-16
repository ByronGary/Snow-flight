# Snow Flights

## Overview
The Snow Flights project is designed to fetch and process weather data using the Open-Meteo API. It provides functionality to retrieve current, hourly, and daily weather information and processes this data into structured formats using pandas DataFrames.

## Installation
To install the required dependencies, run the following command:

```
pip install -r requirements.txt
```

## Usage
To use the Snow Flights package, you can import the `basecode` module from the `snow_flights` package. The main functionality includes fetching weather data for specified coordinates and processing it into usable formats.

### Example
```python
from snow_flights.basecode import openmeteo

# Example usage of the Open-Meteo API client
```

## Testing
Unit tests for the project are located in the `tests` directory. You can run the tests using:

```
pytest tests/test_basecode.py
```

## Contributing
Contributions are welcome! Please feel free to submit a pull request or open an issue for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for more details.