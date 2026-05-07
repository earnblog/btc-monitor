# MACD信号监控系统

基于K线动能理论，监控OKX永续合约的MACD信号，自动推送到钉钉。

## 功能

- 监控交易量超1亿USDT的所有永续合约
- 6个时间周期：5m / 15m / 30m / 1h / 2h / 4h
- 信号类型：MACD远离零轴、背离、零轴穿越、零轴黏合、高概率反弹
- 钉钉推送 + 网页实时查看
- GitHub Actions 每5分钟自动运行

---

## 部署步骤

### 第一步：Fork 或上传代码到你的 GitHub 仓库

把这些文件上传到你的 GitHub 仓库（比如 `btc-monitor`）

### 第二步：配置钉钉 Webhook

1. 打开钉钉，创建一个群（可以只有自己）
2. 群设置 → 智能群助手 → 添加机器人 → 自定义
3. 勾选"自定义关键词"，填入：`MACD`
4. 复制 Webhook 地址

在 GitHub 仓库配置 Secret：
- 进入仓库 → Settings → Secrets and variables → Actions
- 点击 "New repository secret"
- Name: `DINGTALK_WEBHOOK`
- Value: 你的钉钉 Webhook 地址
- 点击 Save

### 第三步：启用 GitHub Actions

1. 进入仓库 → Actions 标签页
2. 如果看到提示，点击 "Enable GitHub Actions"
3. 找到 "MACD Monitor" workflow
4. 点击 "Enable workflow"

第一次可以手动触发测试：点击 "Run workflow"

### 第四步：部署 Streamlit 网页

1. 进入 https://streamlit.io/cloud
2. 用 GitHub 账号登录
3. 点击 "New app"
4. 选择你的仓库，Branch: main，Main file: app.py
5. 点击 Deploy

部署完成后会得到一个网址，手机电脑都能访问。

---

## 文件结构

```
├── app.py                    # Streamlit 网页
├── run_monitor.py            # 主监控脚本（GitHub Actions 调用）
├── requirements.txt          # Python依赖
├── src/
│   ├── signals.py            # 信号计算逻辑
│   ├── okx_data.py           # OKX数据获取
│   └── notifier.py           # 钉钉推送
├── data/
│   ├── signals.json          # 最新信号（自动生成）
│   └── last_run.txt          # 最后运行时间
└── .github/
    └── workflows/
        └── monitor.yml       # GitHub Actions配置
```

---

## 信号说明

| 信号 | 含义 |
|------|------|
| 🔴 强烈建议做空 | 多级别高位共振+顶背离+4H配合 |
| 🟠 建议做空 | 部分级别高位，注意风险 |
| 🟢 强烈建议做多 | 多级别低位共振+底背离+4H配合 |
| 🟡 建议做多 | 部分级别低位，注意风险 |
| 🎯 高概率信号 | 归零轴+EMA52共振，最高优先级 |
| ⏳ 零轴黏合 | 能量积累中，等待方向突破 |
| ⚠️ 观察 | 有隐形背离，谨慎操作 |

---

## 注意事项

- 信号仅供参考，不构成投资建议
- 普通信号4小时内不重复推送
- 高概率信号（归零轴+EMA52）无冷却限制
- GitHub Actions 免费额度每月2000分钟，每5分钟运行一次约消耗900分钟/月，免费额度够用
