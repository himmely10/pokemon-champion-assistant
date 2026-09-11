from html import escape
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel
from ..type_matchups import type_matchups
from ..data.storage import TYPE_NAMES
from .widgets import TYPE_COLORS


class MatchupLabel(QLabel):
    def __init__(self):
        super().__init__()
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setToolTip('仅按当前形态自身属性计算；不含特性、道具、天气和临时属性变化。')
        self.show_types([])

    def show_types(self,types):
        groups=type_matchups(types)
        if groups is None:self.setText('属性克制：待选择宝可梦');return
        parts=[]
        for key,title,color in [('weakness','弱点','#c54959'),('resistance','抵抗','#13826e'),('immune','免疫','#66758a')]:
            badges=[]
            for kind,rate in groups[key]:
                multiplier={0:'0',.25:'¼',.5:'½'}.get(rate,str(int(rate)))
                badges.append(f'<span style="color:{TYPE_COLORS[kind]}"><b>{escape(TYPE_NAMES[kind])} {multiplier}×</b></span>')
            parts.append(f'<b style="color:{color}">{title}</b>　'+('　 '.join(badges) or '无'))
        self.setText('<br>'.join(parts)+'<br><small>仅自身属性，不含特性与道具修正</small>')
