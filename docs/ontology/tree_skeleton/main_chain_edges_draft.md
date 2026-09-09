# 主链边草案（R→F→L→P + 跨层直连）

> 共 98 条边 | 新增 91 | satisfy 31 · realize 29 · allocate 38

## satisfy（31 条）

| 源 | → | 目标 |
|---|---|---|
| R-FSC（功能安全需求（ISO 26262：SG→FSR→TSR→HSR/SSR）） | → | F-OBC-PROTECT（保护功能（过压/欠压/过流/短路/过温/绝缘监测）） |
| R-FSC（功能安全需求（ISO 26262：SG→FSR→TSR→HSR/SSR）） | → | F-DCDC-PROTECT（DCDC 保护功能） |
| R-PERF（性能需求（输入/输出特性/效率/降额）） | → | F-OBC-CHARGE（充电功能（AC-DC 变换/电压调节/电流限制/模式管理）） |
| R-PERF（性能需求（输入/输出特性/效率/降额）） | → | F-OBC-DISCHARGE（放电功能（V2L/V2G/V2H 逆变）） |
| R-PERF（性能需求（输入/输出特性/效率/降额）） | → | F-DCDC-CONV（电压转换/低压输出） |
| R-PERF（性能需求（输入/输出特性/效率/降额）） | → | F-DCDC-REVERSE（反供电/预充放电） |
| R-PROTECT（保护需求（阈值/动作时间/恢复）） | → | F-OBC-PROTECT（保护功能（过压/欠压/过流/短路/过温/绝缘监测）） |
| R-PROTECT（保护需求（阈值/动作时间/恢复）） | → | F-DCDC-PROTECT（DCDC 保护功能） |
| R-SAFETY（电气安全需求（绝缘/耐压/接触电流）） | → | F-OBC-PROTECT（保护功能（过压/欠压/过流/短路/过温/绝缘监测）） |
| R-SAFETY（电气安全需求（绝缘/耐压/接触电流）） | → | F-SYS（系统级功能（OBC+DCDC 协同/故障管理）） |
| R-EMC（EMC 需求） | → | F-SYS（系统级功能（OBC+DCDC 协同/故障管理）） |
| R-ENV（环境需求（温度/湿度/机械/化学）） | → | F-SYS（系统级功能（OBC+DCDC 协同/故障管理）） |
| R-REL（可靠性需求（耐久/寿命/噪声）） | → | F-SYS（系统级功能（OBC+DCDC 协同/故障管理）） |
| R-SW（软件需求（SWRD：功率转换/通信/诊断/刷写）） | → | F-OBC-COMM（通信功能（CAN/ISO15118/UDS）） |
| R-SW（软件需求（SWRD：功率转换/通信/诊断/刷写）） | → | F-OBC-DIAG（诊断功能） |
| R-SW（软件需求（SWRD：功率转换/通信/诊断/刷写）） | → | F-OBC-WAKE（待机唤醒） |
| R-HW（硬件需求（元器件/材料/安规）） | → | F-OBC-CHARGE（充电功能（AC-DC 变换/电压调节/电流限制/模式管理）） |
| R-HW（硬件需求（元器件/材料/安规）） | → | F-DCDC-CONV（电压转换/低压输出） |
| R-IF（接口与通信需求（CAN 矩阵/状态机要求）） | → | F-OBC-CP（控制导引（CP/CC/锁止）） |
| R-IF（接口与通信需求（CAN 矩阵/状态机要求）） | → | F-OBC-COMM（通信功能（CAN/ISO15118/UDS）） |
| R-STD（标准条款（GB/T 40432/24347/18487/ISO14229/企标…全量）） | → | F-OBC-CHARGE（充电功能（AC-DC 变换/电压调节/电流限制/模式管理）） |
| R-STD（标准条款（GB/T 40432/24347/18487/ISO14229/企标…全量）） | → | F-OBC-CP（控制导引（CP/CC/锁止）） |
| R-STD（标准条款（GB/T 40432/24347/18487/ISO14229/企标…全量）） | → | F-DCDC-CONV（电压转换/低压输出） |
| R-SAFETY（电气安全需求（绝缘/耐压/接触电流）） | → | P-HW-MECH-SEAL（密封系统（O型圈/密封垫/密封胶/气密界面）） |
| R-SAFETY（电气安全需求（绝缘/耐压/接触电流）） | → | P-HW-MECH-BUSBAR（铜排/母排（大电流连接/绝缘间隔）） |
| R-HW（硬件需求（元器件/材料/安规）） | → | P-HW-MAG（磁件学科（变压器/电感）） |
| R-HW（硬件需求（元器件/材料/安规）） | → | P-HW-MATERIAL（材料库（金属/塑料/橡胶/磁材）） |
| R-ENV（环境需求（温度/湿度/机械/化学）） | → | P-HW-MECH-SHIELD（屏蔽与防护（EMC屏蔽罩/防尘/防水透气）） |
| R-ENV（环境需求（温度/湿度/机械/化学）） | → | P-HW-THERMAL-POT（灌封与涂覆（灌封胶/三防漆/粘接剂）） |
| R-EMC（EMC 需求） | → | P-HW-MECH-SHIELD（屏蔽与防护（EMC屏蔽罩/防尘/防水透气）） |
| R-EMC（EMC 需求） | → | P-HW-OBC-EMI（EMI 滤波） |

## realize（29 条）

| 源 | → | 目标 |
|---|---|---|
| F-OBC-CHARGE（充电功能（AC-DC 变换/电压调节/电流限制/模式管理）） | → | L-PWRCTRL（功率控制逻辑域（环路/调制/功率级控制逻辑）） |
| F-OBC-DISCHARGE（放电功能（V2L/V2G/V2H 逆变）） | → | L-PWRCTRL（功率控制逻辑域（环路/调制/功率级控制逻辑）） |
| F-OBC-DISCHARGE（放电功能（V2L/V2G/V2H 逆变）） | → | L-STRATEGY-V2L（V2L Inside 策略） |
| F-OBC-CP（控制导引（CP/CC/锁止）） | → | L-STATE（状态管理（OBC/DCDC/休眠唤醒/AC Relay 状态机）） |
| F-OBC-CP（控制导引（CP/CC/锁止）） | → | L-COMM（通信协议逻辑域（CAN/诊断/ISO15118 协议逻辑）） |
| F-OBC-CP（控制导引（CP/CC/锁止）） | → | L-STRATEGY-GPIO（GPIO PWM 回读策略） |
| F-OBC-PROTECT（保护功能（过压/欠压/过流/短路/过温/绝缘监测）） | → | L-FAULT（故障判定逻辑域（检测/判定/恢复逻辑）） |
| F-OBC-PROTECT（保护功能（过压/欠压/过流/短路/过温/绝缘监测）） | → | L-SENSE（采样监测逻辑域（绝缘/温度/采样逻辑）） |
| F-OBC-PROTECT（保护功能（过压/欠压/过流/短路/过温/绝缘监测）） | → | L-STRATEGY-NTC（NTC 查表策略） |
| F-OBC-PROTECT（保护功能（过压/欠压/过流/短路/过温/绝缘监测）） | → | L-STRATEGY-OPTO（光耦黏连检测策略） |
| F-OBC-PROTECT（保护功能（过压/欠压/过流/短路/过温/绝缘监测）） | → | L-STRATEGY-SENSE（采样容差策略） |
| F-OBC-COMM（通信功能（CAN/ISO15118/UDS）） | → | L-COMM（通信协议逻辑域（CAN/诊断/ISO15118 协议逻辑）） |
| F-OBC-DIAG（诊断功能） | → | L-COMM（通信协议逻辑域（CAN/诊断/ISO15118 协议逻辑）） |
| F-OBC-WAKE（待机唤醒） | → | L-SYS（系统管理逻辑域（电源/唤醒/自检逻辑）） |
| F-OBC-WAKE（待机唤醒） | → | L-STATE（状态管理（OBC/DCDC/休眠唤醒/AC Relay 状态机）） |
| F-DCDC-CONV（电压转换/低压输出） | → | L-PWRCTRL（功率控制逻辑域（环路/调制/功率级控制逻辑）） |
| F-DCDC-CONV（电压转换/低压输出） | → | L-STRATEGY-FREQ（抖频策略（DCDC/OBC）） |
| F-DCDC-CONV（电压转换/低压输出） | → | L-STRATEGY-PEAK（峰值功率策略） |
| F-DCDC-REVERSE（反供电/预充放电） | → | L-PWRCTRL（功率控制逻辑域（环路/调制/功率级控制逻辑）） |
| F-DCDC-REVERSE（反供电/预充放电） | → | L-STRATEGY-PRECHARGE（启动预充策略） |
| F-DCDC-PROTECT（DCDC 保护功能） | → | L-FAULT（故障判定逻辑域（检测/判定/恢复逻辑）） |
| F-SYS（系统级功能（OBC+DCDC 协同/故障管理）） | → | L-SYS（系统管理逻辑域（电源/唤醒/自检逻辑）） |
| F-SYS（系统级功能（OBC+DCDC 协同/故障管理）） | → | L-STATE（状态管理（OBC/DCDC/休眠唤醒/AC Relay 状态机）） |
| F-SYS（系统级功能（OBC+DCDC 协同/故障管理）） | → | L-CAL（标定逻辑域（标定参数管理逻辑）） |
| F-OBC-CHARGE（充电功能（AC-DC 变换/电压调节/电流限制/模式管理）） | → | L-STRATEGY-FREQ（抖频策略（DCDC/OBC）） |
| F-OBC-CHARGE（充电功能（AC-DC 变换/电压调节/电流限制/模式管理）） | → | L-STRATEGY-CBC（CBC 策略） |
| F-OBC-CHARGE（充电功能（AC-DC 变换/电压调节/电流限制/模式管理）） | → | L-STRATEGY-PEAK（峰值功率策略） |
| F-OBC-CHARGE（充电功能（AC-DC 变换/电压调节/电流限制/模式管理）） | → | L-STRATEGY-PRECHARGE（启动预充策略） |
| F-OBC-CHARGE（充电功能（AC-DC 变换/电压调节/电流限制/模式管理）） | → | L-STRATEGY-LOWTEMP（低温启机策略） |

## allocate（38 条）

| 源 | → | 目标 |
|---|---|---|
| L-PWRCTRL（功率控制逻辑域（环路/调制/功率级控制逻辑）） | → | P-HW-OBC-PFC（PFC 电路） |
| L-PWRCTRL（功率控制逻辑域（环路/调制/功率级控制逻辑）） | → | P-HW-OBC-DCDC（隔离变换级（LLC）） |
| L-PWRCTRL（功率控制逻辑域（环路/调制/功率级控制逻辑）） | → | P-HW-DCDC-CONV（变换电路） |
| L-PWRCTRL（功率控制逻辑域（环路/调制/功率级控制逻辑）） | → | P-SW-ASW-OBCPWRCTRL（OBCPowerCtrl（OBC功率控制）） |
| L-PWRCTRL（功率控制逻辑域（环路/调制/功率级控制逻辑）） | → | P-SW-ASW-DCDCPWRCTRL（DCDCPowerCtrl（DCDC功率控制）） |
| L-STATE（状态管理（OBC/DCDC/休眠唤醒/AC Relay 状态机）） | → | P-SW-ASW-OBCSTATE（OBCState（状态管理）） |
| L-STATE（状态管理（OBC/DCDC/休眠唤醒/AC Relay 状态机）） | → | P-SW-ASW-DCDCSTATE（DCDCState） |
| L-STATE（状态管理（OBC/DCDC/休眠唤醒/AC Relay 状态机）） | → | P-SW-ASW-SLEEPWAKE（SleepWake（休眠唤醒）） |
| L-FAULT（故障判定逻辑域（检测/判定/恢复逻辑）） | → | P-SW-ASW-OBCFAULTDET（OBCFaultDetect） |
| L-FAULT（故障判定逻辑域（检测/判定/恢复逻辑）） | → | P-SW-ASW-DCDCFAULTDET（DCDCFaultDetect） |
| L-FAULT（故障判定逻辑域（检测/判定/恢复逻辑）） | → | P-SW-ASW-OBCFAULTRPT（OBCFaultReport） |
| L-FAULT（故障判定逻辑域（检测/判定/恢复逻辑）） | → | P-SW-ASW-DCDCFAULTRPT（DCDCFaultReport） |
| L-FAULT（故障判定逻辑域（检测/判定/恢复逻辑）） | → | P-HW-CTRL-PROTECT（保护电路） |
| L-COMM（通信协议逻辑域（CAN/诊断/ISO15118 协议逻辑）） | → | P-SW-ASW-CANREPORT（CANReport） |
| L-COMM（通信协议逻辑域（CAN/诊断/ISO15118 协议逻辑）） | → | P-SW-ASW-CANRCV（CAN_Receive） |
| L-COMM（通信协议逻辑域（CAN/诊断/ISO15118 协议逻辑）） | → | P-SW-BSW-COMM（BSW 通信栈（CAN/LIN/ETH/网络管理）） |
| L-CAL（标定逻辑域（标定参数管理逻辑）） | → | P-SW-ASW-CAL（Calibration（标定）） |
| L-CAL（标定逻辑域（标定参数管理逻辑）） | → | P-CAL（标定数据树（降额曲线/阈值/增益）） |
| L-SENSE（采样监测逻辑域（绝缘/温度/采样逻辑）） | → | P-SW-ASW-ADC（ADCSignal（采样）） |
| L-SENSE（采样监测逻辑域（绝缘/温度/采样逻辑）） | → | P-HW-CTRL-SENSE（采样电路） |
| L-SENSE（采样监测逻辑域（绝缘/温度/采样逻辑）） | → | P-SW-ASW-INSDET（INSDET（绝缘检测）） |
| L-SENSE（采样监测逻辑域（绝缘/温度/采样逻辑）） | → | P-SW-ASW-TEMP（Temp（温度管理）） |
| L-SYS（系统管理逻辑域（电源/唤醒/自检逻辑）） | → | P-HW-CTRL-MCU（MCU/DSP） |
| L-SYS（系统管理逻辑域（电源/唤醒/自检逻辑）） | → | P-SW-ASW-SLEEPWAKE（SleepWake（休眠唤醒）） |
| L-STRATEGY-FREQ（抖频策略（DCDC/OBC）） | → | P-SW-ASW-OBCPWRCTRL（OBCPowerCtrl（OBC功率控制）） |
| L-STRATEGY-FREQ（抖频策略（DCDC/OBC）） | → | P-SW-ASW-DCDCPWRCTRL（DCDCPowerCtrl（DCDC功率控制）） |
| L-STRATEGY-CBC（CBC 策略） | → | P-SW-ASW-OBCPWRCTRL（OBCPowerCtrl（OBC功率控制）） |
| L-STRATEGY-PEAK（峰值功率策略） | → | P-SW-ASW-OBCPWRCTRL（OBCPowerCtrl（OBC功率控制）） |
| L-STRATEGY-PEAK（峰值功率策略） | → | P-SW-ASW-DCDCPWRCTRL（DCDCPowerCtrl（DCDC功率控制）） |
| L-STRATEGY-PRECHARGE（启动预充策略） | → | P-SW-ASW-DCDCPWRCTRL（DCDCPowerCtrl（DCDC功率控制）） |
| L-STRATEGY-NTC（NTC 查表策略） | → | P-SW-ASW-TEMP（Temp（温度管理）） |
| L-STRATEGY-NTC（NTC 查表策略） | → | P-HW-CTRL-SENSE（采样电路） |
| L-STRATEGY-LOWTEMP（低温启机策略） | → | P-SW-ASW-OBCPWRCTRL（OBCPowerCtrl（OBC功率控制）） |
| L-STRATEGY-V2L（V2L Inside 策略） | → | P-SW-ASW-OBCPWRCTRL（OBCPowerCtrl（OBC功率控制）） |
| L-STRATEGY-OPTO（光耦黏连检测策略） | → | P-SW-ASW-OBCFAULTDET（OBCFaultDetect） |
| L-STRATEGY-GPIO（GPIO PWM 回读策略） | → | P-SW-BSW-MCAL（MCAL 驱动（ADC/SPI/GPIO/PWM/WDG）） |
| L-STRATEGY-SENSE（采样容差策略） | → | P-SW-ASW-ADC（ADCSignal（采样）） |
| L-STRATEGY-SENSE（采样容差策略） | → | P-HW-CTRL-SENSE（采样电路） |
