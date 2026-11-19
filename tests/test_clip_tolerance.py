"""The clip's edge tolerance: what the report prints (the tolerance used, in cm, for the SMS 3-sigma method; the
processing buffer in m for the OCCD method)."""
from engine.report import clean_report as cr


def _R(method, buffer_m):
    return {"method": method, "aoi": {"file": "field.geojson", "n_polygons": 1, "area_ac": 100.0, "buffer_m": buffer_m,
                                      "n_outside_buffer": 12, "n_in": 988, "n_output_outside_aoi": 0}}


def test_report_prints_the_s1_edge_tolerance_in_cm():
    """OUT7: a 1 cm tolerance was printed as '+ 0 m buffer' (0 decimals)."""
    t = cr._aoi_text(_R("sms3sigma", 0.01))
    assert "S1 edge tolerance 1 cm" in t and "0 m buffer" not in t
    assert "S1 edge tolerance 0 cm" in cr._aoi_text(_R("sms3sigma", 0.0))
    assert "S1 edge tolerance 2.5 cm" in cr._aoi_text(_R("sms3sigma", 0.025))


def test_report_prints_the_occd_buffer_in_m():
    t = cr._aoi_text(_R("occd", 50.0))
    assert "+ 50 m buffer" in t and "edge tolerance" not in t
    assert "+ 0.5 m buffer" in cr._aoi_text(_R("occd", 0.5))


def test_s1_default_keeps_no_reading_outside_the_boundary(tmp_path):
    """SMS's Clip To Field Boundary removes readings less than 1 cm outside the boundary, which a 1 cm tolerance kept:
    the default edge tolerance is 0. A reading 5 mm outside is clipped, one 5 mm inside is kept; the parameter
    still widens the edge when it is set."""
    import numpy as np
    import shapely
    from engine.clean import aoi, sms3sigma as sms
    from tests.synthetic import make_field
    F = make_field(str(tmp_path / "f"))
    plan = aoi.read_plan(F["boundary"])
    utm = plan.gdf.estimate_utm_crs()
    U = plan.union_in(utm)
    c = U.centroid
    edge = shapely.LineString([(c.x, c.y), (c.x + 1e4, c.y)]).intersection(U.exterior)   # the east edge
    ex, ey = edge.x, edge.y
    x = np.array([ex - 0.005, ex + 0.005])
    y = np.array([ey, ey])
    d = shapely.distance(shapely.points(x, y), U.exterior)
    assert np.all((d > 0.004) & (d < 0.006))                                    # 5 mm either side
    assert sms.DEFAULTS["clip_tolerance_m"] == 0.0
    assert aoi.inside(plan, x, y, utm, sms.DEFAULTS["clip_tolerance_m"]).tolist() == [True, False]
    assert aoi.inside(plan, x, y, utm, 0.01).tolist() == [True, True]


def _R_sms(buffer_m, edge_tolerance_m):
    R = _R("sms3sigma", buffer_m)
    R["sms3sigma"] = {"clip": {"edge_tolerance_m": edge_tolerance_m}}
    return R


def test_report_prints_a_wider_pre_step_buffer_as_a_buffer():
    """An SMS cleaning whose pre-step kept a wider buffer than S1's tolerance (the engine's own 50 m): the buffer in m,
    never 'S1 edge tolerance 5000 cm'."""
    for R in (_R("sms3sigma", 50.0), _R_sms(50.0, 0.0)):
        t = cr._aoi_text(R)
        assert "+ 50 m buffer" in t and "edge tolerance" not in t, t
    assert "S1 edge tolerance 0 cm" in cr._aoi_text(_R_sms(0.0, 0.0))
    assert "S1 edge tolerance 1 cm" in cr._aoi_text(_R_sms(0.01, 0.01))
    assert "+ 0.05 m buffer" in cr._aoi_text(_R_sms(0.05, 0.0))


def test_the_edge_rule_is_named_as_it_is_applied():
    """At tolerance 0 no text says a point within 0 cm of the edge, or on it, is inside; at 1 cm the texts say so."""
    import ast
    import os
    from engine.clean import sms3sigma as sms
    t0, t1 = sms.edge_rule_text(0.0), sms.edge_rule_text(0.01)
    assert "within 0 cm" not in t0 and "inside" not in t0 and "on the edge" in t0 and "clipped" in t0
    assert t1 == "a point within 1 cm of the edge counts as inside"
    assert sms.edge_rule_text(None) == t0
    # the report's field-of-interest paragraph (SMS method)
    for tol, want, never in ((0.0, t0, "within 0 cm"), (0.01, t1, "no edge tolerance")):
        story = []
        cr._section_aoi(story, {}, 2, sms=True, clip={"tolerance_m": tol})
        txt = " ".join(getattr(p, "text", "") for p in story)
        assert want in txt and never not in txt, txt
    # the app's caption names no edge point as inside
    app = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "oced.py")
    tree = ast.parse(open(app, encoding="utf-8").read())
    cap = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
               and getattr(n.targets[0], "id", "") == "SMS3S_TEXT")
    assert "on the edge is inside" not in cap and "Clip To Field Boundary" in cap


def test_a_reading_in_a_gap_between_two_polygons_is_outside_at_the_default(tmp_path):
    """The field of interest is the union of its polygons. Two polygons 5 mm apart: a reading in the gap is clipped at
    the default tolerance 0, as at the edge, and inside at 1 cm (the buffered union closes the gap)."""
    import geopandas as gpd
    import numpy as np
    import shapely
    from engine.clean import aoi, sms3sigma as sms
    utm = "EPSG:32612"
    x0, y0 = 400000.0, 5700000.0
    g = gpd.GeoDataFrame({"name": ["a", "b"]},
                         geometry=[shapely.box(x0, y0, x0 + 100, y0 + 100),
                                   shapely.box(x0 + 100.005, y0, x0 + 200, y0 + 100)], crs=utm).to_crs(4326)
    f = str(tmp_path / "two.geojson")
    g.to_file(f, driver="GeoJSON")
    plan = aoi.read_plan(f)
    x = np.array([x0 + 100.0025, x0 + 50.0, x0 + 150.0])
    y = np.array([y0 + 50.0] * 3)
    U = plan.union_in(utm)
    assert U.distance(shapely.Point(x[0], y[0])) > 0.002                          # in the gap
    assert aoi.inside(plan, x, y, utm, sms.DEFAULTS["clip_tolerance_m"]).tolist() == [False, True, True]
    assert aoi.inside(plan, x, y, utm, 0.01).tolist() == [True, True, True]


def test_the_app_pre_step_cuts_at_the_s1_tolerance_of_the_settings(tmp_path):
    """app/oced.py settings_of (the app's route of the pre-step): aoi.buffer_m = sms3sigma.clip_tolerance_m when it
    is given, the default when it is missing or None (a stored None does not raise)."""
    import ast
    import os
    import types
    from engine import run as er
    from engine.clean import sms3sigma as sms
    app = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "oced.py")
    tree = ast.parse(open(app, encoding="utf-8").read())
    fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "settings_of"]
    bnd = tmp_path / "b.geojson"
    bnd.write_text("{}")
    ns = {"os": os, "er": er, "sms": sms, "ss": types.SimpleNamespace(grower={}, datasets={}),
          "combine_settings": lambda tag: {"on": False}, "boundary_of": lambda tag: {"path": str(bnd)},
          "grower_ticket": lambda G: None, "import_record_of": lambda tag: None,
          "import_min_yield": lambda tag: (None, False), "yields_converted": lambda IM: False}
    exec(compile(ast.Module(fn, []), app, "exec"), ns)
    so = ns["settings_of"]
    assert so("T", {"clip_tolerance_m": 0.05})["aoi"]["buffer_m"] == 0.05
    assert so("T", {"clip_tolerance_m": None})["aoi"]["buffer_m"] == sms.DEFAULTS["clip_tolerance_m"] == 0.0
    assert so("T", {})["aoi"]["buffer_m"] == 0.0
    assert "aoi" not in so("T", {"clip": False})
