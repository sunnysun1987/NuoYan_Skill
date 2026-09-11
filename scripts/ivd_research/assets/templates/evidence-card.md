# {{ title }}

材料ID：{{ material_id }}
证据卡ID：{{ evidence_card_id }}
材料类型：{{ material_type_label }}

## 摘要

{{ summary }}

## 事实

{% for fact in facts %}
- {{ fact }}
{% endfor %}

## 关键摘录

{% for excerpt in key_excerpts %}
- {{ excerpt.text }}（位置：{{ excerpt.location }}）
{% endfor %}

## 指标事实

{% for fact in metric_facts %}
- {{ fact.metric_type_zh }}（{{ fact.metric_type_en }}）：{{ fact.value }}；{{ fact.metric_explanation_zh }}；原文：{{ fact.excerpt }}{% if fact.excerpt_zh %}；中文速读：{{ fact.excerpt_zh }}{% endif %}
{% endfor %}

## 推断

{% for inference in inferences %}
- {{ inference }}
{% endfor %}

## 局限和待复核

{% for limitation in limitations %}
- {{ limitation }}
{% endfor %}
