"""Structural analysis of the house drawing from normalized mouse segments.

The module is deliberately independent from UI, sessions and persistence.  It
does not produce a clinical score: its output is a collection of geometric
features for later review by a specialist.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import atan2, degrees, hypot
from typing import Any, Iterable


ANGLE_TOLERANCE_DEGREES = 20.0
RELATIVE_JOIN_TOLERANCE = 0.04


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Segment:
    start: Point
    end: Point
    source_index: int

    @property
    def length(self) -> float:
        return hypot(self.end.x - self.start.x, self.end.y - self.start.y)


@dataclass(frozen=True)
class Box:
    left: float
    top: float
    right: float
    bottom: float
    segment_indices: frozenset[int]

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def area(self) -> float:
        return self.width * self.height


def analyze_house(lines: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Analyze a house drawing represented by lines in the 0..1 range."""
    segments, rejected = _parse_segments(lines)
    if not segments:
        return _empty_result(rejected)

    tolerance = _drawing_tolerance(segments)
    horizontal = [line for line in segments if _orientation(line) == "horizontal"]
    vertical = [line for line in segments if _orientation(line) == "vertical"]
    diagonal = [line for line in segments if _orientation(line) == "diagonal"]
    rectangles = _find_rectangles(horizontal, vertical, tolerance)
    triangles = _find_triangles(horizontal, diagonal, tolerance)

    body = max(rectangles, key=lambda box: box.area, default=None)
    roof = _select_roof(triangles, body, tolerance)
    window = _select_window(rectangles, body, tolerance)
    annex = _select_annex(rectangles, body, tolerance)
    chimney = _select_chimney(rectangles, horizontal, vertical, roof, body, tolerance)
    cross = _window_cross(window, horizontal, vertical, tolerance)

    used = set()
    for item in (body, roof, window, annex, chimney):
        if item is not None:
            used.update(item.segment_indices)

    features = {
        "body": _feature(body),
        "roof": _feature(roof, touches_body=_roof_touches_body(roof, body, tolerance)),
        "chimney": _feature(chimney, touches_roof=_chimney_touches_roof(chimney, roof, tolerance)),
        "annex": _feature(
            annex,
            side="right" if annex else None,
            left_edge_touches_body=_annex_touches_body(annex, body, tolerance),
        ),
        "window": _feature(window, inside_body=_inside(window, body, tolerance)),
        "window_cross": {
            "found": cross["horizontal"] and cross["vertical"],
            **cross,
        },
    }
    required_ok = (
        features["body"]["found"]
        and features["roof"]["found"] and features["roof"]["touches_body"]
        and features["chimney"]["found"] and features["chimney"]["touches_roof"]
        and features["annex"]["found"] and features["annex"]["left_edge_touches_body"]
        and features["window"]["found"] and features["window"]["inside_body"]
        and features["window_cross"]["found"]
    )
    return {
        "review_required": True,
        "clinical_score": None,
        "structure_complete": required_ok,
        "features": features,
        "counts": {
            "rectangles": len(rectangles),
            "triangles": len(triangles),
            "extra_lines": sum(line.source_index not in used for line in segments),
            "accepted_lines": len(segments),
            "rejected_lines": rejected,
        },
        "tolerance": {
            "join": round(tolerance, 6),
            "angle_degrees": ANGLE_TOLERANCE_DEGREES,
        },
        "notes": "Автоматический балл за дом не выставляется; требуется проверка специалистом.",
    }


def _parse_segments(lines: Iterable[dict[str, Any]]) -> tuple[list[Segment], int]:
    parsed, rejected = [], 0
    for index, item in enumerate(lines):
        try:
            values = tuple(float(item[key]) for key in ("x1", "y1", "x2", "y2"))
        except (KeyError, TypeError, ValueError):
            rejected += 1
            continue
        if not all(0.0 <= value <= 1.0 for value in values):
            rejected += 1
            continue
        line = Segment(Point(values[0], values[1]), Point(values[2], values[3]), index)
        if line.length < 0.005:
            rejected += 1
            continue
        parsed.append(line)
    return parsed, rejected


def _drawing_tolerance(lines: list[Segment]) -> float:
    xs = [point.x for line in lines for point in (line.start, line.end)]
    ys = [point.y for line in lines for point in (line.start, line.end)]
    smaller_side = min(max(xs) - min(xs), max(ys) - min(ys))
    return max(0.008, smaller_side * RELATIVE_JOIN_TOLERANCE)


def _orientation(line: Segment) -> str:
    angle = abs(degrees(atan2(line.end.y-line.start.y, line.end.x-line.start.x))) % 180
    if min(angle, 180-angle) <= ANGLE_TOLERANCE_DEGREES:
        return "horizontal"
    if abs(angle-90) <= ANGLE_TOLERANCE_DEGREES:
        return "vertical"
    return "diagonal"


def _bounds(line: Segment) -> tuple[float, float, float, float]:
    return (min(line.start.x,line.end.x), min(line.start.y,line.end.y),
            max(line.start.x,line.end.x), max(line.start.y,line.end.y))


def _find_rectangles(horizontal: list[Segment], vertical: list[Segment], tolerance: float) -> list[Box]:
    found: list[Box] = []
    for top, bottom in combinations(horizontal, 2):
        t_left,t_top,t_right,_ = _bounds(top)
        b_left,b_top,b_right,_ = _bounds(bottom)
        if abs(t_top-b_top) <= tolerance:
            continue
        left_x=max(t_left,b_left); right_x=min(t_right,b_right)
        if right_x-left_x <= tolerance*2:
            continue
        y1,y2=sorted((t_top,b_top))
        for left, right in combinations(vertical, 2):
            l_left,l_top,_,l_bottom=_bounds(left); r_left,r_top,_,r_bottom=_bounds(right)
            x1,x2=sorted((l_left,r_left))
            if x2-x1 <= tolerance*2:
                continue
            if abs(x1-left_x)>tolerance or abs(x2-right_x)>tolerance:
                continue
            # One physical line may be shared by adjoining shapes.  In that
            # case (the body wall and the annex, for example) the line is
            # longer than the side of the smaller rectangle, so it only has
            # to cover the complete side rather than end at both corners.
            if (l_top > y1+tolerance or l_bottom < y2-tolerance
                    or r_top > y1+tolerance or r_bottom < y2-tolerance):
                continue
            candidate=Box(x1,y1,x2,y2,frozenset((top.source_index,bottom.source_index,left.source_index,right.source_index)))
            if not any(_same_box(candidate, item, tolerance) for item in found):
                found.append(candidate)
    return found


def _find_triangles(horizontal: list[Segment], diagonal: list[Segment], tolerance: float) -> list[Box]:
    found=[]
    for base in horizontal:
        left,base_y,right,_=_bounds(base)
        for first,second in combinations(diagonal,2):
            endpoints1=(first.start,first.end); endpoints2=(second.start,second.end)
            for left_side,right_side in ((endpoints1,endpoints2),(endpoints2,endpoints1)):
                base_left=min(left_side,key=lambda p: hypot(p.x-left,p.y-base_y))
                base_right=min(right_side,key=lambda p: hypot(p.x-right,p.y-base_y))
                apex_left=max(left_side,key=lambda p: hypot(p.x-left,p.y-base_y))
                apex_right=max(right_side,key=lambda p: hypot(p.x-right,p.y-base_y))
                if (_distance(base_left,Point(left,base_y))<=tolerance
                        and _distance(base_right,Point(right,base_y))<=tolerance
                        and _distance(apex_left,apex_right)<=tolerance
                        and apex_left.y < base_y-tolerance):
                    box=Box(left,min(apex_left.y,apex_right.y),right,base_y,
                            frozenset((base.source_index,first.source_index,second.source_index)))
                    if not any(_same_box(box,item,tolerance) for item in found):
                        found.append(box)
    return found


def _select_roof(triangles: list[Box], body: Box | None, tolerance: float) -> Box | None:
    candidates=[item for item in triangles if body is None or (
        item.top < body.top and abs(item.bottom-body.top)<=tolerance*2
        and item.left <= body.left+tolerance*2 and item.right >= body.right-tolerance*2)]
    return max(candidates,key=lambda item:item.area,default=None)


def _select_window(rectangles: list[Box], body: Box | None, tolerance: float) -> Box | None:
    candidates=[item for item in rectangles if item != body and _inside(item,body,tolerance)
                and body is not None and item.area < body.area*.45]
    return max(candidates,key=lambda item:item.area,default=None)


def _select_annex(rectangles: list[Box], body: Box | None, tolerance: float) -> Box | None:
    if body is None: return None
    candidates=[item for item in rectangles if item != body and item.left >= body.right-tolerance*2
                and abs(item.left-body.right)<=tolerance*2 and abs(item.bottom-body.bottom)<=tolerance*3]
    return max(candidates,key=lambda item:item.area,default=None)


def _select_chimney(rectangles: list[Box], horizontal: list[Segment], vertical: list[Segment],
                    roof: Box | None, body: Box | None, tolerance: float) -> Box | None:
    candidates=[item for item in rectangles if item != body and item.top < (body.top if body else 1)
                and _chimney_touches_roof(item,roof,tolerance)
                and _chimney_is_on_reference_side(item,roof,tolerance)]
    if candidates: return max(candidates,key=lambda item:item.height,default=None)
    # The canonical reference has an open lower edge: accept two vertical sides
    # connected by a top edge when both descend into the roof region.
    if roof is None: return None
    for left,right in combinations(vertical,2):
        lx,lt,_,lb=_bounds(left); rx,rt,_,rb=_bounds(right)
        x1,x2=sorted((lx,rx))
        if x2-x1 <= tolerance or max(lb,rb) < roof.top or min(lb,rb) > roof.bottom+tolerance:
            continue
        candidate=Box(x1,min(lt,rt),x2,max(lb,rb),
                      frozenset((left.source_index,right.source_index)))
        if not _chimney_is_on_reference_side(candidate,roof,tolerance):
            continue
        for top in horizontal:
            hl,ht,hr,_=_bounds(top)
            if abs(ht-min(lt,rt))<=tolerance and abs(hl-x1)<=tolerance and abs(hr-x2)<=tolerance:
                return Box(x1,min(lt,rt),x2,max(lb,rb),frozenset((left.source_index,right.source_index,top.source_index)))
    return None


def _window_cross(window: Box | None, horizontal: list[Segment], vertical: list[Segment], tolerance: float) -> dict[str,bool]:
    if window is None: return {"horizontal":False,"vertical":False}
    vertical_crosses=[line for line in vertical
                      if line.source_index not in window.segment_indices
                      and _spans_inside(line,window,"vertical",tolerance)]
    vertical_found=bool(vertical_crosses)
    horizontal_found=False
    for line in horizontal:
        if line.source_index in window.segment_indices:
            continue
        left,top,right,_=_bounds(line)
        if not window.top+tolerance < top < window.bottom-tolerance:
            continue
        full_width=left<=window.left+tolerance and right>=window.right-tolerance
        meets_centre=any(
            (abs(left-_bounds(cross)[0])<=tolerance and right>=window.right-tolerance)
            or (left<=window.left+tolerance and abs(right-_bounds(cross)[0])<=tolerance)
            for cross in vertical_crosses
        )
        if full_width or meets_centre:
            horizontal_found=True
            break
    return {"horizontal":horizontal_found,"vertical":vertical_found}


def _spans_inside(line: Segment, box: Box, orientation: str, tolerance: float) -> bool:
    left,top,right,bottom=_bounds(line)
    if orientation=="horizontal":
        return box.top+tolerance < top < box.bottom-tolerance and left<=box.left+tolerance and right>=box.right-tolerance
    return box.left+tolerance < left < box.right-tolerance and top<=box.top+tolerance and bottom>=box.bottom-tolerance


def _inside(inner: Box | None, outer: Box | None, tolerance: float) -> bool:
    return bool(inner and outer and inner.left>outer.left+tolerance and inner.right<outer.right-tolerance
                and inner.top>outer.top+tolerance and inner.bottom<outer.bottom-tolerance)


def _roof_touches_body(roof: Box | None, body: Box | None, tolerance: float) -> bool:
    return bool(roof and body and abs(roof.bottom-body.top)<=tolerance*2)


def _chimney_touches_roof(chimney: Box | None, roof: Box | None, tolerance: float) -> bool:
    return bool(chimney and roof and chimney.right>=roof.left-tolerance and chimney.left<=roof.right+tolerance
                and chimney.bottom>=roof.top-tolerance and chimney.top<=roof.bottom+tolerance)


def _chimney_is_on_reference_side(chimney: Box | None, roof: Box | None, tolerance: float) -> bool:
    """The reference chimney intersects the right-hand slope of the roof."""
    if chimney is None or roof is None:
        return False
    roof_centre=(roof.left+roof.right)/2
    return chimney.left >= roof_centre-tolerance


def _annex_touches_body(annex: Box | None, body: Box | None, tolerance: float) -> bool:
    return bool(annex and body and abs(annex.left-body.right)<=tolerance*2)


def _feature(item: Box | None, **relations: Any) -> dict[str,Any]:
    result={"found":item is not None,**relations}
    if item: result["bounds"]={"left":item.left,"top":item.top,"right":item.right,"bottom":item.bottom}
    return result


def _same_box(first: Box, second: Box, tolerance: float) -> bool:
    return all(abs(a-b)<=tolerance for a,b in zip(
        (first.left,first.top,first.right,first.bottom),(second.left,second.top,second.right,second.bottom)))


def _distance(first: Point, second: Point) -> float:
    return hypot(first.x-second.x,first.y-second.y)


def _empty_result(rejected: int) -> dict[str,Any]:
    missing={"found":False}
    return {"review_required":True,"clinical_score":None,"structure_complete":False,
            "features":{"body":dict(missing),"roof":dict(missing),"chimney":dict(missing),
                        "annex":dict(missing),"window":dict(missing),
                        "window_cross":{"found":False,"horizontal":False,"vertical":False}},
            "counts":{"rectangles":0,"triangles":0,"extra_lines":0,"accepted_lines":0,"rejected_lines":rejected},
            "tolerance":{"join":0.0,"angle_degrees":ANGLE_TOLERANCE_DEGREES},
            "notes":"Автоматический балл за дом не выставляется; требуется проверка специалистом."}
