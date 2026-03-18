"""
学生行为检测的标签映射与通用工具。

可根据你的训练数据集调整/替换。
默认提供一组常见课堂行为标签，用于将 cls 索引映射成人类可读标签。
"""

from typing import List, Dict, Optional


# 默认的学生行为标签（按你的模型训练类别顺序调整）
DEFAULT_BEHAVIOR_LABELS: List[str] = [
    "head_down",         # 低头
    "phone_usage",       # 看手机/使用手机
    "reading_note",      # 阅读/记笔记
    "hand_raise",        # 举手
    "distracted",        # 左顾右盼/分心
]


# 若需要兼容现有项目的 kind 选择（例如 crop disease 原有的四类），
# 这里也提供一个简单的映射占位；实际使用学生行为模型时建议传 kind="student"
LEGACY_KINDS: Dict[str, List[str]] = {
    "rice": ['Brown_Spot（褐斑病）', 'Rice_Blast（稻瘟病）', 'Bacterial_Blight（细菌性叶枯病）'],
    "corn": ['blight（疫病）', 'common_rust（普通锈病）', 'gray_spot（灰斑病）', 'health（健康）'],
    "strawberry": ['Angular Leafspot（角斑病）', 'Anthracnose Fruit Rot（炭疽果腐病）', 'Blossom Blight（花枯病）', 'Gray Mold（灰霉病）', 'Leaf Spot（叶斑病）', 'Powdery Mildew Fruit（白粉病果）', 'Powdery Mildew Leaf（白粉病叶）'],
    "tomato": ['Early Blight（早疫病）', 'Healthy（健康）', 'Late Blight（晚疫病）', 'Leaf Miner（潜叶病）', 'Leaf Mold（叶霉病）', 'Mosaic Virus（花叶病毒）', 'Septoria（壳针孢属）', 'Spider Mites（蜘蛛螨）', 'Yellow Leaf Curl Virus（黄化卷叶病毒）'],
}


def resolve_labels(kind: Optional[str]) -> List[str]:
    """根据 kind 返回对应的标签列表；未匹配时回退到学生行为默认标签。"""
    if not kind:
        return DEFAULT_BEHAVIOR_LABELS
    k = str(kind).strip().lower()
    if k == "student" or k == "behavior" or k == "classroom":
        return DEFAULT_BEHAVIOR_LABELS
    # 兼容旧项目 kind
    if k in LEGACY_KINDS:
        return LEGACY_KINDS[k]
    return DEFAULT_BEHAVIOR_LABELS
