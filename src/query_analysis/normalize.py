"""
4.1 文本标准化：全角→半角、中文数字→阿拉伯数字、去除冗余标点、大小写归一。
"""
import re
import unicodedata

try:
    import cn2an
    _HAS_CN2AN = True
except ImportError:
    _HAS_CN2AN = False

# 全角 → 半角 映射（常用）
_FULL_TO_HALF = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ　",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ",
)

# 冗余标点：连续重复或可省略的标点
_PUNCT_RE = re.compile(r"[^\w\s]+")


def _full_to_half(s: str) -> str:
    """全角转半角（通用 Unicode 类别 + 数字字母空格）。"""
    result = []
    for c in s:
        if c in "　":
            result.append(" ")
        elif unicodedata.category(c) == "Nd" and unicodedata.numeric(c, None) is not None:
            # 全角数字等
            try:
                result.append(str(int(unicodedata.numeric(c))))
            except (ValueError, TypeError):
                result.append(c)
        elif "\uff01" <= c <= "\uff5e":
            result.append(chr(ord(c) - 0xFEE0))
        else:
            result.append(c)
    return "".join(result)


def _chinese_number_to_arabic(s: str) -> str:
    """中文数字转阿拉伯数字。"""
    if not _HAS_CN2AN:
        return s
    try:
        return cn2an.transform(s, "cn2an")
    except Exception:
        return s


def _normalize_punctuation(s: str) -> str:
    """去除冗余标点：连续标点保留一个，首尾标点去掉。"""
    s = s.strip()
    # 将连续非字母数字空格的字符压成一个空格（保留一个间隔）
    s = _PUNCT_RE.sub(" ", s)
    # 合并多余空格
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize(query: str) -> str:
    """
    文本标准化。
    - 全角→半角
    - 中文数字→阿拉伯数字（如 八六→86）
    - 去除冗余标点、合并空格
    - 大小写归一（英文小写）
    """
    if not query or not query.strip():
        return ""
    s = query.strip()
    s = _full_to_half(s)
    s = _chinese_number_to_arabic(s)
    s = _normalize_punctuation(s)
    return s.lower()
