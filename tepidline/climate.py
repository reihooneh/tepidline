"""The air around each pipe through the day, for a Sydney summer or winter.

Outdoor air follows a daily sine between the month's mean minimum and maximum (Sydney, Observatory
Hill: January about 19.6 to 26.0 °C, July about 8.1 to 16.4 °C; Bureau of Meteorology climate
averages). A roof space adds solar heating through the day, more under a dark roof; floors and
walls stay near indoor temperature. Mains water comes in at the ground's temperature.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DAY = 86400.0

SEASONS = {
    #          out min, out max, indoor, underfloor, mains
    "summer": (19.6, 26.0, 24.0, 21.0, 23.0),
    "winter": (8.1, 16.4, 19.0, 14.0, 15.0),
}
ROOF_GAIN = {("summer", "dark"): 24.0, ("summer", "light"): 12.0, ("winter", "dark"): 11.0, ("winter", "light"): 6.0}


@dataclass(frozen=True)
class Climate:
    season: str = "summer"
    roof: str = "dark"

    @property
    def mains(self) -> float:
        return SEASONS[self.season][4]

    def outdoor(self, t: float) -> float:
        lo, hi = SEASONS[self.season][:2]
        h = (t % DAY) / 3600
        # coldest near 6am, warmest near 3pm
        return (
            (lo + hi) / 2 - (hi - lo) / 2 * math.cos(2 * math.pi * (h - 6) / 18)
            if 6 <= h <= 15
            else (lo + hi) / 2 + (hi - lo) / 2 * math.cos(math.pi * ((h - 15) % 24) / 15)
        )

    def air(self, zone: str, t: float) -> float:
        _, _, indoor, under, _ = SEASONS[self.season]
        h = (t % DAY) / 3600
        if zone == "roof":
            sun = max(0.0, math.sin(math.pi * (h - 7) / 12)) if 7 <= h <= 19 else 0.0
            # the roof space lags the sun a little and cools to just below outdoor air at night
            return self.outdoor(t) + ROOF_GAIN[(self.season, self.roof)] * float(sun**1.3) - (1.0 if sun == 0 else 0.0)
        if zone == "outdoor":
            return self.outdoor(t)
        if zone == "underfloor":
            return under
        swing = 1.5 * math.sin(2 * math.pi * (h - 10) / 24)
        return indoor + swing  # walls and indoors
