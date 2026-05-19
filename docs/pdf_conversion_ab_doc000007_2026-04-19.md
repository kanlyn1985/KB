# PDF 转换 A/B 对比报告

## 测试文档

- 文档: `DOC-000007_QC_T 1036-2016 汽车电源逆变器-免费标准网_www.upbz.net.pdf`
- 大小: `0.872 MB`

## PaddleVL 结果

- 页数: `24`
- block 数: `24`
- 封面关键锚点命中: `4/4`

封面预览:

```text
# 中华人民共和国汽车行业标准

QC/T 1036—2016

汽车电源逆变器

Automotive DC—AC power inverter

<div style="text-align: center;"><img src="imgs/img_in_image_box_77_1363_278_1489.jpg" alt="Image" width="16%" /></div>


2016-04-05 发布

2016-09-01 实施

中华人民共和国工业和信息化部 发布
```

## LLM 结果

### 图像输入

- HTTP 状态: `200`
- 成功判定: `False`
- 关键锚点命中: `0/4`

```text
The user says: "You are performing OCR. Read this page and return only the visible text in markdown, no commentary."

We have to determine what to do. There's no page content given. There's no attached image or URL. It's a command to "read this page". There's no page provided. So we must respond with only visible text in markdown. But we don't have any visible text. Possibly we need to ask for the page content. However the instruction from the user is "You are performing OCR. Read this page and return only the visible text in markdown, no commentary." The assistant should obey. But if there is no page, we can't produce text. We could respond that we need the image. But the instruction says to return only visible text in markdown, no commentary. However the user didn't provide any image. So
```

### PDF 文档输入

- HTTP 状态: `200`
- 成功判定: `False`
- 关键锚点命中: `0/4`

```text
The user says: "Read this PDF and return the first page visible text only in markdown, no commentary." This is a request that presumably references a PDF that is not given. Possibly they will attach a PDF. The user hasn't attached any PDF. The instruction: "Read this PDF and return the first page visible text only in markdown, no commentary." This is ambiguous. If there's no PDF attached, we cannot read it. According to policy, we must handle the situation: we must ask the user to provide the PDF or the content. The request says "Read this PDF". If the PDF is attached, we need to extract text from it. However, the user hasn't provided any PDF in the chat. Possibly they think the PDF is attached or have a link? There's no URL or attachment. So we need to ask for clarification or ask them to
```

## 结论

当前项目配置的 LLM 接口未表现出可用的 PDF/图片直读能力；PaddleVL 可以成功完成整份 PDF 解析并正确命中封面关键锚点。

这意味着当前环境下无法对“真正的 LLM 直读 PDF/图片转换精度”做公平对比，因为项目配置的 LLM 输入链路本身不可用。  
若要继续做真实 A/B，对策有两种：

1. 更换为明确支持 PDF/图片多模态输入的 LLM 接口
2. 将对比目标调整为：
   - PaddleVL 视觉解析
   - 文本层提取 + LLM 结构化整理
