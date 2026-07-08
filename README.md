# 百应店铺成交商品采集工具

本地运行的抖音电商百应“场景分析”成交商品采集工具。支持多店铺、日期筛选、历史场次增量缓存、网页查询，以及带商品图片的 Excel 导出。

## 环境准备

- Windows 10/11
- Python 3.8+
- Google Chrome

安装依赖：

```bat
python -m pip install -r requirements.txt
```

将 `shops.example.txt` 复制为 `shops.txt`，每行填写店铺名称和百应达人主页网址：

```text
店铺名称    https://buyin.jinritemai.com/dashboard/servicehall/daren-profile?uid=...
```

## 启动

双击：

```text
start_web_ui.bat
```

启动脚本会检查 Chrome 调试端口，必要时使用独立用户目录打开 Google Chrome。首次使用需在该 Chrome 窗口内完成百应登录。

网页默认地址：`http://127.0.0.1:8765`

## 数据规则

- 只保留“单场直播结算额”有值的商品。
- 历史直播场次抓取完成后写入本地缓存，再次遇到时直接跳过。
- 当天场次允许重新抓取，以便更新尚未稳定的数据。
- 历史缓存、商品图片、日志和导出文件均保存在 `outputs/`，不会提交到 Git。

## 命令行

先启动调试 Chrome：

```bat
start_baiying_chrome_debug.cmd
```

批量抓取：

```bat
python data_gather.py --raw-cdp --scene-products --shop-list shops.txt --max-pages 2
```

可选日期范围：

```bat
python data_gather.py --raw-cdp --scene-products --shop-list shops.txt --start-date 2026-07-01 --end-date 2026-07-31 --max-pages 2
```

仅根据现有 JSON 重新生成 Excel：

```bat
python data_gather.py --products-xlsx-only
```
