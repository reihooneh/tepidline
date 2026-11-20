"""Two example buildings, written out the way a plumber would draw them."""

from __future__ import annotations

from typing import Any

ROOF_Y = 2.85  # pipes in the roof space lie just above the ceiling
WEEK = [0, 1, 2, 3, 4, 5, 6]
WEEKDAYS = [0, 1, 2, 3, 4]


class Plan:
    def __init__(self, name: str, size: list[float]) -> None:
        self.d: dict[str, Any] = {"name": name, "size": size, "pipes": [], "outlets": [], "tmvs": [], "rooms": []}

    def pipe(self, pid: str, src: str, zone: str, pts: list[list[float]], dn: int = 15, insulation: float = 0) -> str:
        self.d["pipes"].append(
            {"id": pid, "from": src, "zone": zone, "points": pts, "dn": dn, "material": "copper", "insulation": insulation}
        )
        return pid

    def drop(self, pid: str, src: str, roof_pts: list[list[float]], to: list[float], dn: int = 15) -> str:
        """A run through the roof space, then down inside a wall to an outlet."""
        top = [to[0], ROOF_Y, to[2]]
        self.pipe(pid + "-r", src, "roof", [*roof_pts, top], dn)
        return self.pipe(pid, "pipe:" + pid + "-r", "wall", [top, to], dn)

    def outlet(
        self,
        oid: str,
        name: str,
        kind: str,
        at: list[float],
        hot: str | None,
        cold: str | None,
        uses: list[tuple[float, float, list[int]]] | list[tuple[float, int, list[int]]],
    ) -> None:
        self.d["outlets"].append(
            {
                "id": oid,
                "name": name,
                "kind": kind,
                "at": at,
                "hot": hot,
                "cold": cold,
                "uses": [{"at": a, "minutes": m, "days": d} for a, m, d in uses],
            }
        )

    def room(self, name: str, box: list[float]) -> None:
        self.d["rooms"].append({"name": name, "box": box})


def family_house() -> dict[str, Any]:
    """A single-storey Sydney house: storage heater outside, one tempering valve beside it feeding
    every bathroom through the roof space, and the cold water up there too."""
    p = Plan("Family house, Sydney", [16, 11, 2.7])
    p.d["setpoint"] = 60
    p.d["heater_at"] = [16.4, 0, 1.6]
    p.d["meter_at"] = [0.5, 0, -0.6]
    rooms: list[tuple[str, list[float]]] = [
        ("Living", [0, 0, 9, 6]),
        ("Kitchen", [9, 0, 13, 4]),
        ("Laundry", [13, 0, 16, 3]),
        ("Hall", [9, 4, 16, 7]),
        ("Bathroom", [2, 7, 5.5, 11]),
        ("Guest bathroom", [6, 7.6, 8.4, 11]),
        ("Bedroom 2", [0, 6, 2, 11]),
        ("Bedroom 3", [8.4, 7, 11, 11]),
        ("Ensuite", [11, 7, 14, 11]),
        ("Main bedroom", [14, 3, 16, 11]),
    ]
    for name, box in rooms:
        p.room(name, box)
    # Hot, straight from the heater: kitchen and laundry (tempering is optional there).
    p.pipe("h-out", "hot", "outdoor", [[16.4, 0.6, 1.6], [16.0, 0.6, 1.6]], dn=20, insulation=13)
    p.pipe("h-trunk", "pipe:h-out", "underfloor", [[16.0, 0.6, 1.6], [16.0, -0.3, 1.6], [14.5, -0.3, 1.6]], dn=20)
    p.pipe("h-laundry", "pipe:h-trunk", "wall", [[14.5, -0.3, 1.6], [14.5, 0.9, 0.3]])
    p.pipe("h-kitchen", "pipe:h-trunk", "underfloor", [[14.5, -0.3, 1.6], [11.0, -0.3, 1.6], [11.0, 0.9, 0.4]])
    # Cold mains: in at the front, along under the floor to the back, up into the roof for the bathrooms.
    p.pipe("c-main", "cold", "underfloor", [[0.5, -0.3, -0.6], [0.5, -0.3, 1.0], [12.0, -0.3, 1.0]], dn=20)
    p.pipe("c-kitchen", "pipe:c-main", "wall", [[12.0, -0.3, 1.0], [11.2, 0.9, 0.4]])
    p.pipe("c-back", "pipe:c-main", "underfloor", [[12.0, -0.3, 1.0], [16.0, -0.3, 1.0], [16.0, -0.3, 2.4]], dn=20)
    p.pipe("c-laundry", "pipe:c-back", "wall", [[16.0, -0.3, 2.4], [14.7, 0.9, 0.3]])
    p.pipe("c-tmv", "pipe:c-back", "outdoor", [[16.0, -0.3, 2.4], [16.4, 0.5, 2.4]], insulation=13)
    p.pipe("c-up", "pipe:c-back", "wall", [[16.0, -0.3, 2.4], [15.6, ROOF_Y, 2.4]], dn=20)
    p.pipe("c-roof", "pipe:c-up", "roof", [[15.6, ROOF_Y, 2.4], [15.6, ROOF_Y, 6.6], [10.0, ROOF_Y, 6.6]], dn=20)
    p.pipe("c-roof2", "pipe:c-roof", "roof", [[10.0, ROOF_Y, 6.6], [5.0, ROOF_Y, 6.6]], dn=20)
    # The tempering valve beside the heater, then up and across the roof space.
    p.d["tmvs"].append({"id": "tmv", "hot": "h-tmv", "cold": "c-tmv", "set": 50, "at": [16.4, 0.5, 2.0]})
    p.pipe("h-tmv", "pipe:h-out", "outdoor", [[16.0, 0.6, 1.6], [16.4, 0.5, 2.0]], insulation=13)
    p.pipe("t-up", "tmv:tmv", "outdoor", [[16.4, 0.5, 2.0], [16.4, ROOF_Y, 2.0], [15.8, ROOF_Y, 2.0]])
    p.pipe("t-roof", "pipe:t-up", "roof", [[15.8, ROOF_Y, 2.0], [15.8, ROOF_Y, 6.9], [12.5, ROOF_Y, 6.9]])
    p.pipe("t-roof2", "pipe:t-roof", "roof", [[12.5, ROOF_Y, 6.9], [7.2, ROOF_Y, 6.9]])
    p.pipe("t-roof3", "pipe:t-roof2", "roof", [[7.2, ROOF_Y, 6.9], [4.0, ROOF_Y, 6.9]])
    # Ensuite
    ens_sh = p.drop("t-ens-sh", "pipe:t-roof", [[12.5, ROOF_Y, 6.9]], [13.4, 1.0, 10.6])
    ens_bs = p.drop("t-ens-bs", "pipe:t-roof", [[12.5, ROOF_Y, 6.9]], [11.6, 0.9, 7.3])
    c_ens_sh = p.drop("c-ens-sh", "pipe:c-roof", [[10.0, ROOF_Y, 6.6], [13.6, ROOF_Y, 6.6]], [13.6, 1.0, 10.6])
    c_ens_bs = p.drop("c-ens-bs", "pipe:c-roof", [[10.0, ROOF_Y, 6.6], [11.8, ROOF_Y, 6.6]], [11.8, 0.9, 7.3])
    # Guest bathroom
    g_sh = p.drop("t-g-sh", "pipe:t-roof2", [[7.2, ROOF_Y, 6.9]], [7.8, 1.0, 10.5])
    g_bs = p.drop("t-g-bs", "pipe:t-roof2", [[7.2, ROOF_Y, 6.9]], [6.6, 0.9, 8.0])
    c_g_sh = p.drop("c-g-sh", "pipe:c-roof2", [[7.6, ROOF_Y, 6.6]], [8.0, 1.0, 10.5])
    c_g_bs = p.drop("c-g-bs", "pipe:c-roof2", [[6.8, ROOF_Y, 6.6]], [6.8, 0.9, 8.0])
    # Main bathroom
    m_sh = p.drop("t-m-sh", "pipe:t-roof3", [[4.0, ROOF_Y, 6.9], [4.0, ROOF_Y, 9.5]], [2.5, 1.0, 10.4])
    m_bt = p.drop("t-m-bt", "pipe:t-roof3", [[4.0, ROOF_Y, 6.9]], [4.6, 0.6, 10.5])
    m_bs = p.drop("t-m-bs", "pipe:t-roof3", [[4.0, ROOF_Y, 6.9]], [4.8, 0.9, 7.4])
    c_m_sh = p.drop("c-m-sh", "pipe:c-roof2", [[5.0, ROOF_Y, 6.6], [2.7, ROOF_Y, 6.6]], [2.7, 1.0, 10.4])
    c_m_bt = p.drop("c-m-bt", "pipe:c-roof2", [[5.0, ROOF_Y, 6.6]], [4.8, 0.6, 10.5])
    c_m_bs = p.drop("c-m-bs", "pipe:c-roof2", [[5.0, ROOF_Y, 6.6]], [5.0, 0.9, 7.4])

    p.outlet(
        "ens-shower",
        "Ensuite shower",
        "shower",
        [13.4, 1.0, 10.6],
        ens_sh,
        c_ens_sh,
        [(6.0, 7, WEEKDAYS), (8.5, 8, [5, 6]), (21.5, 8, WEEK)],
    )
    p.outlet("ens-basin", "Ensuite basin", "basin", [11.7, 0.9, 7.3], ens_bs, c_ens_bs, [(6.2, 1, WEEK), (21.7, 1, WEEK)])
    p.outlet(
        "main-shower",
        "Bathroom shower",
        "shower",
        [2.6, 1.0, 10.4],
        m_sh,
        c_m_sh,
        [(6.6, 8, WEEKDAYS), (7.1, 8, WEEKDAYS), (9.0, 9, [5, 6]), (19.6, 9, [1, 3, 5, 6])],
    )
    p.outlet("bath", "Bath", "bath", [4.7, 0.6, 10.5], m_bt, c_m_bt, [(19.0, 6, [0, 2, 4])])
    p.outlet(
        "main-basin",
        "Bathroom basin",
        "basin",
        [4.9, 0.9, 7.4],
        m_bs,
        c_m_bs,
        [(6.8, 1, WEEK), (7.3, 1, WEEK), (20.0, 1, WEEK), (21.0, 1, WEEK)],
    )
    p.outlet("guest-shower", "Guest shower", "shower", [7.9, 1.0, 10.5], g_sh, c_g_sh, [(8.0, 8, [5])])
    p.outlet("guest-basin", "Guest basin", "basin", [6.7, 0.9, 8.0], g_bs, c_g_bs, [(8.2, 1, [5])])
    p.outlet(
        "kitchen",
        "Kitchen sink",
        "kitchen",
        [11.1, 0.9, 0.4],
        "h-kitchen",
        "c-kitchen",
        [(7.5, 2, WEEK), (12.5, 1, WEEK), (18.0, 3, WEEK), (19.8, 4, WEEK)],
    )
    p.outlet("laundry", "Laundry tub", "laundry", [14.6, 0.9, 0.3], "h-laundry", "c-laundry", [(9.0, 4, [5, 6])])
    return p.d


def care_wing() -> dict[str, Any]:
    """An aged-care wing: a 45 °C thermostatic mixing valve in the plant room feeds eight ensuites
    along a corridor ceiling. Two rooms are empty until new residents arrive on Monday."""
    p = Plan("Aged-care wing", [30, 12, 2.7])
    p.d["setpoint"] = 65
    p.d["cap_rare"] = False  # the empty rooms will have residents again
    p.d["heater_at"] = [-0.8, 0, 6]
    p.d["meter_at"] = [-0.8, 0, 7.5]
    p.room("Plant room", [0, 5, 2, 7])
    p.room("Corridor", [2, 5, 30, 7])
    p.d["tmvs"].append({"id": "tmv", "hot": "h-feed", "cold": "c-feed", "set": 45, "at": [1.0, 1.2, 6.0]})
    p.pipe("h-feed", "hot", "indoor", [[-0.8, 1.2, 6.0], [1.0, 1.2, 6.0]], dn=20, insulation=13)
    p.pipe("c-in", "cold", "indoor", [[-0.8, 0.4, 7.5], [1.2, 0.4, 7.5]], dn=25)
    p.pipe("c-feed", "pipe:c-in", "indoor", [[1.2, 0.4, 7.5], [1.0, 1.2, 6.0]])
    p.pipe("t-up", "tmv:tmv", "indoor", [[1.0, 1.2, 6.0], [1.0, ROOF_Y, 6.0], [2.0, ROOF_Y, 6.0]], dn=20, insulation=13)
    p.pipe("c-up", "pipe:c-in", "indoor", [[1.2, 0.4, 7.5], [1.2, ROOF_Y, 6.4], [2.0, ROOF_Y, 6.4]], dn=25)
    prev_t, prev_c = "t-up", "c-up"
    week = WEEK
    empty = {3, 6}
    for i in range(8):
        x0 = 2 + i * 3.5
        side = 0 if i % 2 == 0 else 1
        x = x0 + 1.75
        top = side == 0
        z_room = 2.5 if top else 9.5
        p.room(f"Room {i + 1}{' (empty until Monday)' if i in empty else ''}", [x0, 0 if top else 7, x0 + 3.5, 5 if top else 12])
        t_seg = p.pipe(f"t-c{i}", f"pipe:{prev_t}", "roof", [[x0, ROOF_Y, 6.0], [x, ROOF_Y, 6.0]], dn=20, insulation=13)
        c_seg = p.pipe(f"c-c{i}", f"pipe:{prev_c}", "roof", [[x0, ROOF_Y, 6.4], [x, ROOF_Y, 6.4]], dn=20)
        if i < 7:
            t_seg2 = p.pipe(f"t-d{i}", f"pipe:{t_seg}", "roof", [[x, ROOF_Y, 6.0], [x0 + 3.5, ROOF_Y, 6.0]], dn=20, insulation=13)
            c_seg2 = p.pipe(f"c-d{i}", f"pipe:{c_seg}", "roof", [[x, ROOF_Y, 6.4], [x0 + 3.5, ROOF_Y, 6.4]], dn=20)
            prev_t, prev_c = t_seg2, c_seg2
        zb = z_room + (-1.2 if top else 1.2)
        sh = p.drop(f"t-sh{i}", f"pipe:{t_seg}", [[x, ROOF_Y, 6.0]], [x + 0.8, 1.0, zb])
        bs = p.drop(f"t-bs{i}", f"pipe:{t_seg}", [[x, ROOF_Y, 6.0]], [x - 0.8, 0.9, zb])
        csh = p.drop(f"c-sh{i}", f"pipe:{c_seg}", [[x, ROOF_Y, 6.4]], [x + 1.0, 1.0, zb])
        cbs = p.drop(f"c-bs{i}", f"pipe:{c_seg}", [[x, ROOF_Y, 6.4]], [x - 0.6, 0.9, zb])
        shower_at = 7.0 + (i % 4) * 0.6
        # An empty room's taps sit until a new resident arrives on Monday.
        uses_sh = [(9.0, 10, [0])] if i in empty else [(shower_at, 10, week)]
        uses_bs = (
            [(8.7, 1, [0])] if i in empty else [(shower_at - 0.3, 1, week), (12.0, 1, week), (20.0 + (i % 3) * 0.3, 1, week)]
        )
        p.outlet(f"r{i + 1}-shower", f"Room {i + 1} shower", "shower", [x + 0.9, 1.0, zb], sh, csh, uses_sh)
        p.outlet(f"r{i + 1}-basin", f"Room {i + 1} basin", "basin", [x - 0.7, 0.9, zb], bs, cbs, uses_bs)
    return p.d


EXAMPLES = {"house": family_house, "care": care_wing}
