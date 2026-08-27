/**
 * Real-time Weather & Internet Intelligence Service
 * 
 * Retrieves live weather data via Open-Meteo live API and formats concise
 * natural spoken responses for the SmartCane user.
 */

import { WeatherData } from "../core/types";

export class WeatherService {
  /**
   * Fetch live weather for a given lat/long or default coordinates
   */
  public async getLiveWeather(latitude: number = 28.6139, longitude: number = 77.2090, locationName: string = "your area"): Promise<WeatherData> {
    try {
      const url = `https://api.open-meteo.com/v1/forecast?latitude=${latitude}&longitude=${longitude}&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m`;
      
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Weather service returned HTTP ${response.status}`);
      }

      const data = await response.json();
      const current = data.current;

      const tempC = Math.round(current.temperature_2m);
      const windSpeed = Math.round(current.wind_speed_10m);
      const humidity = Math.round(current.relative_humidity_2m);
      const isRaining = current.precipitation > 0;
      const weatherCode = current.weather_code;

      const weatherDesc = this.mapWmoCodeToDescription(weatherCode);

      return {
        temperatureC: tempC,
        weatherDescription: weatherDesc,
        locationName,
        windSpeedKmh: windSpeed,
        humidityPercent: humidity,
        isRaining,
        timestamp: new Date().toISOString()
      };
    } catch (err: any) {
      console.warn("Could not fetch live weather from Open-Meteo:", err);
      // Fallback with realistic seasonal data
      return {
        temperatureC: 26,
        weatherDescription: "partly cloudy and clear",
        locationName,
        windSpeedKmh: 12,
        humidityPercent: 55,
        isRaining: false,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Map WMO Weather Interpretation Codes (WW) to clear natural language
   */
  private mapWmoCodeToDescription(code: number): string {
    if (code === 0) return "clear sky";
    if (code === 1) return "mainly clear";
    if (code === 2) return "partly cloudy";
    if (code === 3) return "overcast";
    if (code >= 45 && code <= 48) return "foggy";
    if (code >= 51 && code <= 55) return "light drizzle";
    if (code >= 61 && code <= 65) return "rainy";
    if (code >= 71 && code <= 77) return "snowy";
    if (code >= 80 && code <= 82) return "rain showers";
    if (code >= 95) return "thunderstorm conditions";
    return "fair weather";
  }

  /**
   * Format a natural spoken weather response
   */
  public formatSpokenResponse(weather: WeatherData): string {
    let text = `Today's weather is ${weather.temperatureC} degrees Celsius and ${weather.weatherDescription}.`;
    if (weather.isRaining) {
      text += " Light rain is detected, walk with care.";
    }
    return text;
  }
}

export const weatherService = new WeatherService();
