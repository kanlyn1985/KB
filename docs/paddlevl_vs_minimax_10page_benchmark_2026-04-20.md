# PaddleVL vs MiniMax understand_image 十页对比报告

## 测试范围

- 文档: `GBT+18487.1-2023.pdf`
- 文档页数: `157`
- 抽样页: `1, 18, 36, 53, 70, 88, 105, 122, 140, 157`
- 抽样数: `10`
- 评分方式: `由于该PDF很多页面的内嵌文本层存在乱码，本次不使用文本层做参考答案。评分改为同页图像盲评：同一张页面图分别评估 PaddleVL 输出与 MiniMax understand_image 输出。`

## 平均分

| 路径 | 忠实度 | 完整度 | 术语/数字准确性 | 结构可读性 | 总分 |
|---|---:|---:|---:|---:|---:|
| PaddleVL | 2.20 | 2.20 | 2.90 | 2.10 | 46.50 |
| MiniMax understand_image | 4.60 | 4.90 | 5.00 | 4.90 | 96.30 |

## 总体结论

- 胜出路径: `minimax_understand_image`

## 分页结果

### 第 1 页

- PaddleVL: `75.0` 分 | 问题: `遗漏了左上角的 ICS 43.040.99 和 CCS T 35 编号; 遗漏了底部的发布机构名称（国家市场监督管理总局、国家标准化管理委员会）及“发布”字样; 将标题中的全角冒号“：”转写为了半角冒号“:”; 将原本分两行显示的中文标题合并到了一行`
- MiniMax understand_image: `100.0` 分 | 问题: `无明显问题`

### 第 18 页

- PaddleVL: `75.0` 分 | 问题: `无明显问题`
- MiniMax understand_image: `93.0` 分 | 问题: `在[来源：...]部分，原文在年份后使用的是点号（.），如“2008.3.3.159”，而转写稿统一改为了逗号，如“2008, 3.3.159”。`

### 第 36 页

- PaddleVL: `67.0` 分 | 问题: `候选文本虚构了一个庞大的数据表格来对应图片中的曲线图，图片中并无这些具体的数值文字。; 漏掉了页眉编号 GB/T 18487.1—2023。; 漏掉了右下角的页码 29。; 漏掉了图表图例‘指尖到脚’。`
- MiniMax understand_image: `93.0` 分 | 问题: `候选转写中包含了一行描述性文字 '![接触时间-在单一故障条件下的直流电压图表](image_link)'，这属于对图片内容的总结或补充，违反了指令中'不要补充图片里没有的文字'的要求。`

### 第 53 页

- PaddleVL: `80.0` 分 | 问题: `Missing top document header: GB/T 18487.1—2023; Incorrect transcription of symbol 'Dci' as 'Deci'; Superscript footnote markers in table cells (e.g., a, b, c, d) are transcribed as normal characters or a '*' symbol; The table footnotes are merged into a single paragraph, losing the original separate line structure`
- MiniMax understand_image: `100.0` 分 | 问题: `无明显问题`

### 第 70 页

- PaddleVL: `84.0` 分 | 问题: `缺少页眉文字 'GB/T 18487.1—2023'; 时序 3.1 中的图例文字 '触发条件：充电准备就绪' 被遗漏; 时间列中的多个时间范围表达式（如 '(T6-T5)=0s(T7-T6)≤3s'）合并在了一起，缺少空格或换行分隔; 表格结构在处理‘触发条件’时与原图不一致，3.2 和 4 中将其拆分为独立行，而 3.1 中则直接缺失; 缺少页码 '63'`
- MiniMax understand_image: `93.0` 分 | 问题: `在3.1和3.2的‘条件’栏中，图片原文为‘转到’，被转写为了‘转变为’。`

### 第 88 页

- PaddleVL: `84.0` 分 | 问题: `漏掉了页眉 GB/T 18487.1—2023 和页码 81; 将 C.4.6.5 错误转录为 C.4.5.5; 在数字、符号周围添加了图片中不存在的 LaTeX 格式代码（如 $...$）; 在标题 C.4.7 前添加了 Markdown 标记 ####`
- MiniMax understand_image: `100.0` 分 | 问题: `部分标点符号使用了半角字符（如半角逗号、分号、冒号），而原图为全角字符。; 为各级条目编号额外添加了加粗格式，原图中并非加粗显示。`

### 第 105 页

- PaddleVL: `0.0` 分 | 问题: `无明显问题`
- MiniMax understand_image: `87.0` 分 | 问题: `无明显问题`

### 第 122 页

- PaddleVL: `0.0` 分 | 问题: `无明显问题`
- MiniMax understand_image: `100.0` 分 | 问题: `无明显问题`

### 第 140 页

- PaddleVL: `0.0` 分 | 问题: `候选文本完全为空，没有任何转写内容。`
- MiniMax understand_image: `97.0` 分 | 问题: `The circuit diagram labels are transcribed into a table format which does not reflect their actual spatial relationship or electrical connectivity, though the text content is preserved accurately.; Minor spacing inconsistency in '检测点 2' (with space) versus '检测点1' and '检测点3' (without space) as compared to the image.`

### 第 157 页

- PaddleVL: `0.0` 分 | 问题: `候选文本内容为空，未能提取图片中的任何文字。`
- MiniMax understand_image: `100.0` 分 | 问题: `无明显问题`

