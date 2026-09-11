"""Level-50 reference speed tiers. No assumptions about an opponent's actual build."""

SPEED_TIERS = [
    ("极速围巾", 32, 11, True, "32 点速度培养点、加速性格、讲究围巾 ×1.5"),
    ("极速", 32, 11, False, "32 点速度培养点、加速性格"),
    ("满速围巾", 32, 10, True, "32 点速度培养点、中性性格、讲究围巾 ×1.5"),
    ("满速", 32, 10, False, "32 点速度培养点、中性性格"),
    ("无投", 0, 10, False, "0 点速度培养点、中性性格"),
    ("下降", 0, 9, False, "0 点速度培养点、减速性格；不是速度下降一级"),
]


def reference_speed(base, points=0, nature_tenths=10, scarf=False):
    if type(base) is not int or not 1 <= base <= 255:
        raise ValueError("速度种族值必须为 1–255 的整数")
    if type(points) is not int or not 0 <= points <= 32 or nature_tenths not in (9, 10, 11):
        raise ValueError("不支持的速度培养条件")
    speed = (base + 20 + points) * nature_tenths // 10
    return speed * 3 // 2 if scarf else speed


def speed_lines(base):
    return [reference_speed(base, points, nature, scarf) for _, points, nature, scarf, _ in SPEED_TIERS]
