import importlib.util
import os

from PIL import Image

from sudoku_robot import config


def test_benchmark_chart_script_measures_and_draws(tmp_path):
    spec = importlib.util.spec_from_file_location("make_benchmark_chart",
                                                  os.path.join(config.SCRIPTS_DIR, "make_benchmark_chart.py"))
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    out = tmp_path / "chart.png"
    script.draw_chart(script.measure(1), 1, str(out))      # one run each: fast, still every solver x puzzle
    with Image.open(out) as img:
        assert img.size[0] > 1000 and img.size[1] > 800
