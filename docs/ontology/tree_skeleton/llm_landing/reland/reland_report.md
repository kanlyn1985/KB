# review_queue 全量 LLM 重新落位报告
- 模型: deepseek-v4-flash | 文档: 1705 | 内容单元: 225420
- LLM 归属率: 176937/225420 = 78.5%
- 复核队列: 48483 | 批次失败: 0
- LLM 用量: {"input_tokens": 29929, "output_tokens": 276073, "calls": 299, "errors": 0, "model": "deepseek-v4-flash"}

## LLM 落位按节点 TOP 30

- G-PROD-ASSEMBLY 装配工艺（压装/螺纹紧固/涂胶/组装）: 27656
- G-PROD-POTTING 灌封涂覆工艺（灌胶/点胶/三防）: 13758
- G-VERIFY-CAE CAE仿真验证（热仿真/模态/流阻/强度）: 9843
- G-METHOD-CAE-STRUCT 结构仿真方法（模态/强度/疲劳）: 8397
- Q-PROBLEM 问题记录（问题排查/踩坑记录）: 8317
- G-DEV 开发过程树（RFQ→EVT1→EVT2→ET→PT0→PT1→PPAP→SOP）: 6865
- G-VERIFY-VIBRATION 振动与冲击测试（振动/跌落/扫频）: 5183
- G-VERIFY-DIM 尺寸检测（全尺寸/CPK/三坐标/检具）: 4438
- G-VERIFY-THERMAL 热测试（温升/热循环/热冲击/红外）: 3852
- G-VERIFY 验证活动树（测试/检测/试验）: 3694
- Q-LESSON 经验教训（项目复盘/FAQ/最佳实践）: 3645
- P-HW-MECH-CONNECTOR 连接器与接插件（高压/低压/信号/防呆）: 3166
- G-METHOD-TOL 公差分析方法（尺寸链/GD&T/公差带）: 3151
- G-METHOD-CAE-THERMAL 热仿真方法（Flotherm/热阻网络/CFD）: 2996
- G-VERIFY-ENV 环境测试（高温/低温/湿热/盐雾/防尘）: 2926
- G-PROD 生产过程树（PCBA/组装/生产测试/试制）: 2923
- G-VERIFY-ELECTRICAL 电气测试（耐压/绝缘/安规/接触电阻）: 2795
- G-METHOD-DFM DFM/DFA设计方法（可制造性/可装配性）: 2548
- P-HW-MECH 结构件（壳体/水道/密封/连接器/铜排/屏蔽）: 2488
- G-METHOD-TOOL 工具使用方法（gitlab/Matlab/Polarion/测试工具）: 2087
- G-VERIFY-AIRTIGHT 气密与泄漏测试（气密/保压/氦检/水检）: 2080
- P-HW-MECH-FASTENER 紧固件（螺钉/螺栓/螺母/螺柱/卡扣）: 2076
- G-ASSET 可复用资产（代码资产/文档模板/CBB设计标准）: 2032
- P-HW-MAG 磁件学科（变压器/电感）: 1934
- G-METHOD-CAE-FLUID 流阻仿真方法（水冷流道/风道）: 1872
- P-HW-THERMAL-TIM 导热界面材料（导热垫/硅脂/相变材料）: 1810
- P-HW-OBC-EMI EMI 滤波: 1664
- R-ENV 环境需求（温度/湿度/机械/化学）: 1660
- G-PROD-CASTING 压铸工艺（模具/压铸参数/浇道）: 1579
- G-VERIFY-REL 可靠性试验（耐久/寿命/老化/温循）: 1568

## 复核队列按原因 TOP 20

- [4663] 无实质内容（仅HTML注释）
- [3380] 无实质内容
- [2705] 无实质内容（HTML注释）
- [2595] 无实质内容，仅HTML注释
- [402] 仅HTML注释，无实质内容
- [402] 无实质内容，仅为HTML注释
- [378] 无实质内容（仅 HTML 注释）
- [345] 无实质内容，仅HTML注释。
- [334] 无实质内容（仅HTML注释）。
- [309] 仅日期标题，无实质内容
- [236] 无实质内容，仅为不支持的DingTalk块注释
- [236] 仅标题，无实质内容
- [228] 无实质内容（钉钉块注释）
- [221] 无实质内容，仅标题
- [205] 无实质内容（仅注释）
- [176] 无实质内容（DingTalk 块注释）
- [143] LLM 未返回 (19/20 条已返回)
- [135] 无实质内容（不支持的DingTalk块）
- [127] 无实质内容，仅为不支持的DingTalk块注释。
- [97] 标题，无实质内容