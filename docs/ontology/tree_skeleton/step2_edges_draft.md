# Step2 边草案（验证闭环 + 硬边）

> 共 73 条 | verify 42 · produce 24 · instance-of 2 · issue-on 5

## verify（42 条）

| 源 | → | 目标 |
|---|---|---|
| G-VERIFY-THERMAL（热测试（温升/热循环/热冲击/红外）） | → | P-HW-THERMAL-HEATSINK（散热器（铝挤/压铸/翅片/铲齿）） |
| G-VERIFY-THERMAL（热测试（温升/热循环/热冲击/红外）） | → | P-HW-THERMAL-TIM（导热界面材料（导热垫/硅脂/相变材料）） |
| G-VERIFY-THERMAL（热测试（温升/热循环/热冲击/红外）） | → | P-HW-THERMAL-FAN（风冷部件（风扇/风道/格栅）） |
| G-VERIFY-VIBRATION（振动与冲击测试（振动/跌落/扫频）） | → | P-HW-MECH-HOUSING（壳体（压铸/钣金/机加工/注塑壳体）） |
| G-VERIFY-VIBRATION（振动与冲击测试（振动/跌落/扫频）） | → | P-HW-MECH-BRACKET（支架/托架/安装结构（安装板/法兰/减震支架）） |
| G-VERIFY-VIBRATION（振动与冲击测试（振动/跌落/扫频）） | → | P-HW-MECH-FASTENER（紧固件（螺钉/螺栓/螺母/螺柱/卡扣）） |
| G-VERIFY-AIRTIGHT（气密与泄漏测试（气密/保压/氦检/水检）） | → | P-HW-MECH-SEAL（密封系统（O型圈/密封垫/密封胶/气密界面）） |
| G-VERIFY-AIRTIGHT（气密与泄漏测试（气密/保压/氦检/水检）） | → | P-HW-MECH-HOUSING（壳体（压铸/钣金/机加工/注塑壳体）） |
| G-VERIFY-AIRTIGHT（气密与泄漏测试（气密/保压/氦检/水检）） | → | P-HW-MECH-WATERWAY（水道系统（水道板/水嘴/进出水口/流道设计）） |
| G-VERIFY-ENV（环境测试（高温/低温/湿热/盐雾/防尘）） | → | P-HW-MECH-SHIELD（屏蔽与防护（EMC屏蔽罩/防尘/防水透气）） |
| G-VERIFY-ENV（环境测试（高温/低温/湿热/盐雾/防尘）） | → | P-HW-THERMAL-POT（灌封与涂覆（灌封胶/三防漆/粘接剂）） |
| G-VERIFY-ENV（环境测试（高温/低温/湿热/盐雾/防尘）） | → | P-HW-MECH-HOUSING（壳体（压铸/钣金/机加工/注塑壳体）） |
| G-VERIFY-DIM（尺寸检测（全尺寸/CPK/三坐标/检具）） | → | P-HW-MECH-HOUSING（壳体（压铸/钣金/机加工/注塑壳体）） |
| G-VERIFY-DIM（尺寸检测（全尺寸/CPK/三坐标/检具）） | → | P-HW-MECH-WATERWAY（水道系统（水道板/水嘴/进出水口/流道设计）） |
| G-VERIFY-DIM（尺寸检测（全尺寸/CPK/三坐标/检具）） | → | P-HW-MECH-BRACKET（支架/托架/安装结构（安装板/法兰/减震支架）） |
| G-VERIFY-DIM（尺寸检测（全尺寸/CPK/三坐标/检具）） | → | P-HW-MECH-BUSBAR（铜排/母排（大电流连接/绝缘间隔）） |
| G-VERIFY-REL（可靠性试验（耐久/寿命/老化/温循）） | → | P-HW-MAG（磁件学科（变压器/电感）） |
| G-VERIFY-REL（可靠性试验（耐久/寿命/老化/温循）） | → | P-HW-MECH-FASTENER（紧固件（螺钉/螺栓/螺母/螺柱/卡扣）） |
| G-VERIFY-REL（可靠性试验（耐久/寿命/老化/温循）） | → | P-HW-THERMAL-TIM（导热界面材料（导热垫/硅脂/相变材料）） |
| G-VERIFY-CAE（CAE仿真验证（热仿真/模态/流阻/强度）） | → | P-HW-MECH-HOUSING（壳体（压铸/钣金/机加工/注塑壳体）） |
| G-VERIFY-CAE（CAE仿真验证（热仿真/模态/流阻/强度）） | → | P-HW-MECH-WATERWAY（水道系统（水道板/水嘴/进出水口/流道设计）） |
| G-VERIFY-CAE（CAE仿真验证（热仿真/模态/流阻/强度）） | → | P-HW-MECH-BRACKET（支架/托架/安装结构（安装板/法兰/减震支架）） |
| G-VERIFY-ELECTRICAL（电气测试（耐压/绝缘/安规/接触电阻）） | → | P-HW-OBC-PFC（PFC 电路） |
| G-VERIFY-ELECTRICAL（电气测试（耐压/绝缘/安规/接触电阻）） | → | P-HW-OBC-DCDC（隔离变换级（LLC）） |
| G-VERIFY-ELECTRICAL（电气测试（耐压/绝缘/安规/接触电阻）） | → | P-HW-OBC-EMI（EMI 滤波） |
| G-VERIFY-ELECTRICAL（电气测试（耐压/绝缘/安规/接触电阻）） | → | P-HW-OBC-ACRELAY（AC 继电器） |
| G-VERIFY-ELECTRICAL（电气测试（耐压/绝缘/安规/接触电阻）） | → | P-HW-CTRL-SENSE（采样电路） |
| G-VERIFY-ELECTRICAL（电气测试（耐压/绝缘/安规/接触电阻）） | → | P-HW-MECH-BUSBAR（铜排/母排（大电流连接/绝缘间隔）） |
| G-VERIFY-ELECTRICAL（电气测试（耐压/绝缘/安规/接触电阻）） | → | P-HW-MECH-CONNECTOR（连接器与接插件（高压/低压/信号/防呆）） |
| G-VERIFY-THERMAL（热测试（温升/热循环/热冲击/红外）） | → | R-ENV（环境需求（温度/湿度/机械/化学）） |
| G-VERIFY-THERMAL（热测试（温升/热循环/热冲击/红外）） | → | R-REL（可靠性需求（耐久/寿命/噪声）） |
| G-VERIFY-VIBRATION（振动与冲击测试（振动/跌落/扫频）） | → | R-ENV（环境需求（温度/湿度/机械/化学）） |
| G-VERIFY-VIBRATION（振动与冲击测试（振动/跌落/扫频）） | → | R-REL（可靠性需求（耐久/寿命/噪声）） |
| G-VERIFY-AIRTIGHT（气密与泄漏测试（气密/保压/氦检/水检）） | → | R-ENV（环境需求（温度/湿度/机械/化学）） |
| G-VERIFY-AIRTIGHT（气密与泄漏测试（气密/保压/氦检/水检）） | → | R-SAFETY（电气安全需求（绝缘/耐压/接触电流）） |
| G-VERIFY-ENV（环境测试（高温/低温/湿热/盐雾/防尘）） | → | R-ENV（环境需求（温度/湿度/机械/化学）） |
| G-VERIFY-DIM（尺寸检测（全尺寸/CPK/三坐标/检具）） | → | R-HW（硬件需求（元器件/材料/安规）） |
| G-VERIFY-REL（可靠性试验（耐久/寿命/老化/温循）） | → | R-REL（可靠性需求（耐久/寿命/噪声）） |
| G-VERIFY-CAE（CAE仿真验证（热仿真/模态/流阻/强度）） | → | R-PERF（性能需求（输入/输出特性/效率/降额）） |
| G-VERIFY-CAE（CAE仿真验证（热仿真/模态/流阻/强度）） | → | R-ENV（环境需求（温度/湿度/机械/化学）） |
| G-VERIFY-ELECTRICAL（电气测试（耐压/绝缘/安规/接触电阻）） | → | R-SAFETY（电气安全需求（绝缘/耐压/接触电流）） |
| G-VERIFY-ELECTRICAL（电气测试（耐压/绝缘/安规/接触电阻）） | → | R-EMC（EMC 需求） |

## produce（24 条）

| 源 | → | 目标 |
|---|---|---|
| G-PROD-CASTING（压铸工艺（模具/压铸参数/浇道）） | → | P-HW-MECH-HOUSING（壳体（压铸/钣金/机加工/注塑壳体）） |
| G-PROD-CASTING（压铸工艺（模具/压铸参数/浇道）） | → | P-HW-THERMAL-HEATSINK（散热器（铝挤/压铸/翅片/铲齿）） |
| G-PROD-MACHINING（机加工（CNC/钻孔/攻丝/公差控制）） | → | P-HW-MECH-HOUSING（壳体（压铸/钣金/机加工/注塑壳体）） |
| G-PROD-MACHINING（机加工（CNC/钻孔/攻丝/公差控制）） | → | P-HW-MECH-BRACKET（支架/托架/安装结构（安装板/法兰/减震支架）） |
| G-PROD-MACHINING（机加工（CNC/钻孔/攻丝/公差控制）） | → | P-HW-THERMAL-HEATSINK（散热器（铝挤/压铸/翅片/铲齿）） |
| G-PROD-MACHINING（机加工（CNC/钻孔/攻丝/公差控制）） | → | P-HW-MECH-WATERWAY（水道系统（水道板/水嘴/进出水口/流道设计）） |
| G-PROD-SHEET（钣金工艺（冲压/折弯/焊接/铆接）） | → | P-HW-MECH-HOUSING（壳体（压铸/钣金/机加工/注塑壳体）） |
| G-PROD-SHEET（钣金工艺（冲压/折弯/焊接/铆接）） | → | P-HW-MECH-BRACKET（支架/托架/安装结构（安装板/法兰/减震支架）） |
| G-PROD-SHEET（钣金工艺（冲压/折弯/焊接/铆接）） | → | P-HW-MECH-SHIELD（屏蔽与防护（EMC屏蔽罩/防尘/防水透气）） |
| G-PROD-INJECTION（注塑工艺（模具/注塑参数/脱模）） | → | P-HW-MECH-HOUSING（壳体（压铸/钣金/机加工/注塑壳体）） |
| G-PROD-INJECTION（注塑工艺（模具/注塑参数/脱模）） | → | P-HW-MECH-CONNECTOR（连接器与接插件（高压/低压/信号/防呆）） |
| G-PROD-INJECTION（注塑工艺（模具/注塑参数/脱模）） | → | P-HW-MECH-BRACKET（支架/托架/安装结构（安装板/法兰/减震支架）） |
| G-PROD-SURFACE（表面处理工艺（阳极/电镀/喷涂/钝化）） | → | P-HW-MECH-HOUSING（壳体（压铸/钣金/机加工/注塑壳体）） |
| G-PROD-SURFACE（表面处理工艺（阳极/电镀/喷涂/钝化）） | → | P-HW-MATERIAL-SURFACE（表面处理（阳极氧化/电镀/喷粉/三价铬钝化）） |
| G-PROD-POTTING（灌封涂覆工艺（灌胶/点胶/三防）） | → | P-HW-THERMAL-POT（灌封与涂覆（灌封胶/三防漆/粘接剂）） |
| G-PROD-POTTING（灌封涂覆工艺（灌胶/点胶/三防）） | → | P-HW-CTRL（控制板） |
| G-PROD-ASSEMBLY（装配工艺（压装/螺纹紧固/涂胶/组装）） | → | P-HW-MECH-FASTENER（紧固件（螺钉/螺栓/螺母/螺柱/卡扣）） |
| G-PROD-ASSEMBLY（装配工艺（压装/螺纹紧固/涂胶/组装）） | → | P-HW-MECH-CONNECTOR（连接器与接插件（高压/低压/信号/防呆）） |
| G-PROD-ASSEMBLY（装配工艺（压装/螺纹紧固/涂胶/组装）） | → | P-HW-MECH-BUSBAR（铜排/母排（大电流连接/绝缘间隔）） |
| G-PROD-ASSEMBLY（装配工艺（压装/螺纹紧固/涂胶/组装）） | → | P-HW-MAG（磁件学科（变压器/电感）） |
| G-PROD-ASSEMBLY（装配工艺（压装/螺纹紧固/涂胶/组装）） | → | P-HW-OBC-PFC（PFC 电路） |
| G-PROD-ASSEMBLY（装配工艺（压装/螺纹紧固/涂胶/组装）） | → | P-HW-OBC-DCDC（隔离变换级（LLC）） |
| G-PROD-ASSEMBLY（装配工艺（压装/螺纹紧固/涂胶/组装）） | → | P-HW-CTRL（控制板） |
| G-PROD-PACK（包装工艺（包装/防护/周转/防静电）） | → | P-ROOT（P 物理分解树（主骨架）） |

## instance-of（2 条）

| 源 | → | 目标 |
|---|---|---|
| M-CCU（CCU 型号（OBC+DCDC+逆变集成）） | → | P-ROOT（P 物理分解树（主骨架）） |
| M-SW40（SW4.0 软件平台（富特）） | → | P-SW（软件树） |

## issue-on（5 条）

| 源 | → | 目标 |
|---|---|---|
| Q-PROBLEM-FAILURE（失效分析（失效/断裂/开裂/破损）） | → | P-HW-MECH-HOUSING（壳体（压铸/钣金/机加工/注塑壳体）） |
| Q-PROBLEM-DEFECT（工艺缺陷（缺陷/气泡/溢胶/氧化）） | → | P-HW-MECH-HOUSING（壳体（压铸/钣金/机加工/注塑壳体）） |
| Q-PROBLEM-DEFECT（工艺缺陷（缺陷/气泡/溢胶/氧化）） | → | P-HW-THERMAL-POT（灌封与涂覆（灌封胶/三防漆/粘接剂）） |
| Q-PROBLEM-TEST（测试异常（不合格/超差/NG）） | → | P-HW-CTRL（控制板） |
| Q-FAILURE（失效模式（FMEA 相关）） | → | P-HW-MECH-HOUSING（壳体（压铸/钣金/机加工/注塑壳体）） |
