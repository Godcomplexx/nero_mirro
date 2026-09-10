from neuro_mirror.screening.executive_scoring import analyze_house


def _line(x1,y1,x2,y2):
    return {"x1":x1,"y1":y1,"x2":x2,"y2":y2}


def canonical_house():
    return [
        _line(.15,.35,.70,.35), _line(.15,.35,.15,.90), _line(.70,.35,.70,.90), _line(.15,.90,.70,.90),
        _line(.15,.35,.42,.08), _line(.42,.08,.70,.35),
        _line(.50,.20,.50,.03), _line(.50,.03,.59,.03), _line(.59,.03,.59,.25),
        _line(.70,.62,.84,.62), _line(.84,.62,.84,.90), _line(.70,.90,.84,.90), _line(.70,.62,.70,.90),
        _line(.32,.52,.53,.52), _line(.32,.52,.32,.70), _line(.53,.52,.53,.70), _line(.32,.70,.53,.70),
        _line(.425,.52,.425,.70), _line(.32,.61,.53,.61),
    ]


def test_canonical_house_exposes_all_required_features_without_score():
    result=analyze_house(canonical_house())
    assert result["clinical_score"] is None
    assert result["review_required"] is True
    assert result["features"]["body"]["found"]
    assert result["features"]["roof"]["touches_body"]
    assert result["features"]["chimney"]["touches_roof"]
    assert result["features"]["annex"]["left_edge_touches_body"]
    assert result["features"]["window"]["inside_body"]
    assert result["features"]["window_cross"]["found"]


def test_annex_can_share_the_long_body_wall():
    lines=canonical_house()
    del lines[12]
    result=analyze_house(lines)
    assert result["features"]["body"]["found"]
    assert result["features"]["annex"]["left_edge_touches_body"]


def test_window_horizontal_crossbar_can_run_from_centre_to_edge():
    lines=canonical_house()
    lines[-1]=_line(.425,.61,.53,.61)
    result=analyze_house(lines)
    assert result["features"]["window_cross"]["vertical"]
    assert result["features"]["window_cross"]["horizontal"]
    assert result["features"]["window_cross"]["found"]


def test_annex_on_left_is_not_accepted():
    lines=canonical_house()
    lines[9:13]=[_line(.01,.62,.15,.62),_line(.01,.62,.01,.90),_line(.01,.90,.15,.90),_line(.15,.62,.15,.90)]
    result=analyze_house(lines)
    assert result["features"]["annex"]["found"] is False


def test_chimney_on_left_slope_is_not_accepted():
    lines=canonical_house()
    lines[6:9]=[_line(.25,.20,.25,.03),_line(.25,.03,.34,.03),_line(.34,.03,.34,.25)]
    result=analyze_house(lines)
    assert result["features"]["roof"]["found"]
    assert result["features"]["chimney"]["found"] is False


def test_window_outside_body_is_not_accepted():
    lines=canonical_house()
    lines[13:19]=[_line(.74,.40,.83,.40),_line(.74,.40,.74,.52),_line(.83,.40,.83,.52),
                  _line(.74,.52,.83,.52),_line(.785,.40,.785,.52),_line(.74,.46,.83,.46)]
    result=analyze_house(lines)
    assert result["features"]["window"]["found"] is False


def test_small_hand_jitter_is_tolerated():
    lines=canonical_house()
    lines[0]=_line(.151,.349,.699,.352)
    lines[1]=_line(.149,.351,.152,.899)
    result=analyze_house(lines)
    assert result["features"]["body"]["found"]


def test_invalid_and_empty_input_is_safe():
    result=analyze_house([_line(-1,0,2,1),{}])
    assert result["structure_complete"] is False
    assert result["counts"]["rejected_lines"]==2
