import time
import pandas as pd
from playwright.sync_api import sync_playwright
import os
import shutil
import re

def run():
    # 1. 准备工作：创建截图目录（用于调试），初始化CSV文件
    screenshot_dir = "debug_screenshots"
    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)

    output_file = "guangdong_cosmetics.csv"
    # 如果文件不存在，写入表头
    if not os.path.exists(output_file):
        df = pd.DataFrame(columns=["产品名称", "企业名称", "注册证号", "批件状态", "产品执行标准全文"])
        df.to_csv(output_file, index=False, encoding='utf-8-sig')

    # 2. 启动 Playwright
    with sync_playwright() as p:
        print("正在启动浏览器...")
        browser = p.chromium.launch(headless=False, slow_mo=1000, args=['--start-maximized'])

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True
        )
        page = context.new_page()

        url = "https://www.nmpa.gov.cn/datasearch/home-index.html?itemId=ff8080818046502f0180f934f6873f78#category=hzp"
        print(f"正在打开网页: {url}")

        try:
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as e:
            print(f"网页加载可能有延迟: {e}")

        # 3. 筛选“广东省”
        print("等待页面初始化 (5秒)...")
        page.wait_for_timeout(5000)

        current_page = page

        print("正在尝试筛选 '广东省'...")
        try:
            # 尝试点击“广东省”
            guangdong_btn = page.locator("text=广东").first
            if guangdong_btn.count() > 0:
                with context.expect_page(timeout=10000) as new_page_info:
                    guangdong_btn.click(timeout=5000)

                try:
                    new_popup = new_page_info.value
                    new_popup.wait_for_load_state()
                    print("检测到新窗口弹出，切换到新窗口操作。")
                    current_page = new_popup
                except:
                    print("点击后未检测到新窗口，继续在当前页面操作。")
            else:
                print("未找到'广东'按钮，请手动点击！(等待 15 秒)")
                page.wait_for_timeout(15000)
                if len(context.pages) > 1:
                    current_page = context.pages[-1]
                    print("检测到新窗口，切换过去。")

        except Exception as e:
            print(f"筛选操作出现异常: {e}")
            print("请手动选择广东省... (等待 10 秒)")
            page.wait_for_timeout(10000)
            if len(context.pages) > 1:
                current_page = context.pages[-1]

        # 4. 开始分页抓取
        page_num = 1
        page = current_page
        page.wait_for_load_state("domcontentloaded")

        while True:
            print(f"\n>>> 正在处理第 {page_num} 页 <<<")

            try:
                page.wait_for_selector("tr", timeout=10000)
            except:
                print("等待表格行超时，可能页面加载慢或已无数据。")

            rows = page.locator("tr.el-table__row").all()
            if not rows:
                print("未找到 el-table__row，尝试通用 tr...")
                rows = page.locator("tr").all()

            print(f"本页共检测到 {len(rows)} 行数据。")

            processed_count = 0

            for i, row in enumerate(rows):
                try:
                    # 策略：直接从列表页提取基本信息
                    # 假设列表结构：序号 | 产品名称 | 注册人 | 注册证号 | 批件状态 | 详情
                    cells = row.locator("td").all()

                    # 简单的列索引判断，如果列数不够跳过
                    if len(cells) < 6:
                        continue

                    p_name = cells[1].inner_text().strip()
                    ent_name = cells[2].inner_text().strip()
                    reg_no = cells[3].inner_text().strip()
                    status = cells[4].inner_text().strip()

                    # 过滤非当前批件
                    if "当前批件" not in status:
                        continue

                    print(f"处理: {p_name} | {status}")

                    # 点击详情
                    detail_btn = cells[-1].locator("button, a").first # 最后一列通常是详情按钮
                    if detail_btn.count() == 0:
                         detail_btn = row.locator("text=详情").first

                    if detail_btn.count() == 0:
                        print("  未找到详情按钮，跳过")
                        continue

                    # 进入详情页
                    print("  进入详情页获取标准信息...")
                    detail_page = None
                    try:
                        with context.expect_page(timeout=10000) as detail_page_info:
                            detail_btn.click()
                        detail_page = detail_page_info.value
                        detail_page.wait_for_load_state("domcontentloaded")
                        # 等待关键内容，稍微稳一点
                        detail_page.wait_for_timeout(3000)
                    except:
                        print("  详情页打开失败，跳过")
                        continue

                    # --- 提取执行标准 (PDF页面) ---
                    formula_text = "无"
                    try:
                        # 寻找“产品执行的标准”那一行的“查看”按钮
                        target_row_keywords = ["产品执行的标准", "技术要求"]
                        found_btn = False

                        view_btn = None
                        for kw in target_row_keywords:
                            row_std = detail_page.locator(f"tr:has-text('{kw}')").first
                            if row_std.count() > 0:
                                view_btn = row_std.locator("text=查看").first
                                if view_btn.count() > 0:
                                    break

                        if view_btn and view_btn.count() > 0:
                            print("  点击查看标准PDF...")

                            # 这里不再是弹窗 dialog，而是新窗口打开 PDF 预览
                            with context.expect_page(timeout=15000) as pdf_page_info:
                                view_btn.click()

                            pdf_page = pdf_page_info.value
                            pdf_page.wait_for_load_state()
                            pdf_page.wait_for_timeout(3000)

                            current_url = pdf_page.url
                            print(f"  PDF预览页URL: {current_url}")

                            # 尝试提取 PDF 链接
                            # URL 格式: .../preview-pdf.html?url=...
                            if "url=" in current_url:
                                try:
                                    actual_pdf_url = current_url.split("url=")[1]
                                    formula_text = f"PDF链接: {actual_pdf_url}"

                                    # 尝试获取页面上的文本（如果有）
                                    # 某些 PDF 预览器会把文字渲染在 div.textLayer 中
                                    try:
                                        text_layer = pdf_page.locator(".textLayer, #viewerContainer").first
                                        if text_layer.count() > 0:
                                            content = text_layer.inner_text()
                                            if len(content) > 20:
                                                formula_text = f"内容摘要: {content[:500]}... [完整链接]: {actual_pdf_url}"
                                    except:
                                        pass
                                except:
                                    pass
                            else:
                                formula_text = f"预览页URL: {current_url}"

                            pdf_page.close()
                        else:
                            formula_text = "详情页无查看按钮"

                    except Exception as e:
                        formula_text = f"标准提取出错: {e}"
                        # 截图留证
                        detail_page.screenshot(path=f"{screenshot_dir}/error_pdf_{page_num}_{i}.png")

                    # 写入 CSV
                    new_row = {
                        "产品名称": p_name,
                        "企业名称": ent_name,
                        "注册证号": reg_no,
                        "批件状态": status,
                        "产品执行标准全文": formula_text
                    }
                    df = pd.DataFrame([new_row])
                    df.to_csv(output_file, mode='a', header=False, index=False, encoding='utf-8-sig')

                    # 关闭详情页
                    detail_page.close()

                    processed_count += 1

                except Exception as e:
                    print(f"行处理未知错误: {e}")

            if processed_count == 0:
                print("本页没有采集到有效数据。")

            # 翻页逻辑
            print("尝试翻页...")
            try:
                next_btn = page.locator("button.btn-next").first
                if next_btn.count() > 0:
                    if next_btn.get_attribute("disabled") is not None:
                        print("已到达最后一页。")
                        break
                    next_btn.click()
                    page_num += 1
                    page.wait_for_timeout(3000)
                else:
                    next_btn_alt = page.locator("text=>").last
                    if next_btn_alt.count() > 0:
                        next_btn_alt.click()
                        page_num += 1
                        page.wait_for_timeout(3000)
                    else:
                        print("未找到下一页按钮，结束。")
                        break
            except Exception as e:
                print(f"翻页失败: {e}")
                break

        print(f"任务完成！数据已保存至 {output_file}")
        browser.close()

if __name__ == "__main__":
    run()
