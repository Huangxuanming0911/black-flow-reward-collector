# 黑流树海战后奖励采集器

这是一个只读的 PC 画面采集工具，用于统计《明日方舟》集成战略“沉沦者的黑流树海”战斗结束后的资源奖励。

它不会点击、控制或修改游戏，只会：

1. 低频读取“明日方舟”窗口画面；
2. 识别稳定的“成功通过”和战后“收下”奖励页面；
3. 保存原始证据截图；
4. 离开奖励页面后弹出确认窗口；
5. 将审核结果追加到 JSONL、CSV 和分组汇总 JSON。

## 安装

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

## 启动

先打开明日方舟 PC 客户端，再运行：

```powershell
.\.venv\Scripts\blackflow-reward-collector.exe
```

主窗口可预设下一场的来源层数、所在环境和战斗类型。若预设不准确，可在战后弹窗中修改。

## 统计边界

- “误入奇境内部”是位置环境，不与普通/紧急/Boss 等战斗类别混为一个字段。
- 局内宝箱和宝物怪第一版不自动识别，战后必须选择“无、宝箱、宝物怪、两者都有、不确定”之一。
- 有额外来源但无法说明具体掉落的样本会保留证据，但不会进入基础奖励均值。
- “希望上限+6”“可携带干员数+1”等升级效果单独记录，不算作战斗随机掉落。
- 自动识别结果永远是预填值，只有点击“确认并保存”后才进入正式统计。

## 输出

默认写入：

```text
data/records/rewards.jsonl
data/records/rewards.csv
data/records/summary.json
data/records/screenshots/<sample-id>/
```

`rewards.jsonl` 是原始事实源；CSV 方便表格查看；`summary.json` 提供按层数、环境和战斗类型分组的基础统计。

