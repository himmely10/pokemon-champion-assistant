"""Level-50 reference speed tiers. No assumptions about an opponent's actual build."""

SPEED_TIERS = [
    ("极速围巾", 32, 11, True, "32 点速度培养点、加速性格、讲究围巾 ×1.5"),
    ("满速围巾", 32, 10, True, "32 点速度培养点、中性性格、讲究围巾 ×1.5"),
    ("极速", 32, 11, False, "32 点速度培养点、加速性格"),
    ("满速", 32, 10, False, "32 点速度培养点、中性性格"),
    ("无投", 0, 10, False, "0 点速度培养点、中性性格"),
    ("下降", 0, 9, False, "0 点速度培养点、减速性格；不是速度下降一级"),
]


def reference_speed(base, points=0, nature_tenths=10, scarf=False, *, stage=0,
                    tailwind=False, ability='__none__', ability_on=False,
                    weather='', terrain='', status=''):
    if type(base) is not int or not 1 <= base <= 255:
        raise ValueError("速度种族值必须为 1–255 的整数")
    if type(points) is not int or not 0 <= points <= 32 or nature_tenths not in (9, 10, 11):
        raise ValueError("不支持的速度培养条件")
    speed = (base + 20 + points) * nature_tenths // 10
    if type(stage) is not int or not -6 <= stage <= 6:
        raise ValueError('速度等级须为 -6 至 +6')
    if ability is None or any(type(v) is not bool for v in (scarf,tailwind,ability_on)):
        raise ValueError('速度情景条件尚未确认')
    if weather not in ('','Sun','Rain','Sand','Snow') or terrain not in ('','Electric','Grassy','Misty','Psychic') or status not in ('','par','brn','psn','tox','slp','frz'):
        raise ValueError('天气、场地或异常状态尚未确认或无效')
    speed = speed * (2 + max(stage,0)) // (2 + max(-stage,0))
    modifier = 1
    if tailwind: modifier *= 2
    active_unburden = ability == 'unburden' and ability_on
    scene_speed_ability = ability in {
        'chlorophyll','swift-swim','sand-rush','slush-rush','surge-surfer'
    } and ability_on
    if active_unburden or scene_speed_ability or (ability,weather) in {
        ('chlorophyll','Sun'),('swift-swim','Rain'),('sand-rush','Sand'),('slush-rush','Snow')
    } or (ability == 'surge-surfer' and terrain == 'Electric'):
        modifier *= 2
    elif ability == 'quick-feet' and (status or ability_on): modifier *= 1.5
    elif ability in {'protosynthesis','quark-drive'} and ability_on: modifier *= 1.5
    elif ability == 'slow-start' and ability_on: modifier *= .5
    if scarf and not active_unburden: modifier *= 1.5
    # Cartridge rounding: exact halves round down; paralysis follows modifiers.
    value = speed * modifier
    speed = int(value) + (value % 1 > .5)
    if status == 'par' and ability != 'quick-feet': speed //= 2
    return min(10000,speed)


def speed_lines(base, **conditions):
    return [reference_speed(base, points, nature, scarf, **conditions) for _, points, nature, scarf, _ in SPEED_TIERS]
