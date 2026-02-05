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
    # 更新表头，增加有效期至
    if not os.path.exists(output_file):
        df = pd.DataFrame(columns=["产品名称", "企业名称", "注册证号", "批准日期", "有效期至", "状态", "产品执行标准全文"])
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
                    row_text = row.inner_text()

                    if "产品名称" in row_text and "注册人" in row_text:
                        continue

                    status = "未知"
                    if "当前批件" in row_text:
                        status = "当前批件"
                    elif "历史" in row_text or "过期" in row_text:
                        status = "历史批件"
                    elif "注销" in row_text:
                        status = "注销"

                    if status != "当前批件":
                        continue

                    detail_btn = row.locator("text=详情").first
                    if detail_btn.count() == 0:
                        detail_btn = row.locator("button").last

                    if detail_btn.count() == 0:
                        continue

                    print(f"正在抓取第 {i+1} 行详情...")

                    detail_page = None
                    try:
                        with context.expect_page(timeout=5000) as detail_page_info:
                            detail_btn.click()
                        detail_page = detail_page_info.value
                    except:
                        # 没有新页面弹出
                        detail_page = page
                        page.wait_for_timeout(2000)

                    detail_page.wait_for_load_state("domcontentloaded")
                    detail_page.wait_for_timeout(1500)

                    # --- 详情页数据提取函数 (优化版) ---
                    def safe_get_text(keywords):
                        """
                        根据关键词提取对应的值。
                        策略：找到包含关键词的表格行(tr)，然后获取该行中关键词单元格的下一个单元格。
                        """
                        if isinstance(keywords, str):
                            keywords = [keywords]

                        for kw in keywords:
                            try:
                                # 策略 1: 基于表格行查找
                                # 找到包含关键词的行. 使用 first 匹配最靠前的
                                target_row = detail_page.locator(f"tr:has-text('{kw}')").first

                                if target_row.count() > 0:
                                    # 获取该行所有单元格 td 或 th
                                    cells = target_row.locator("td, th").all()
                                    for idx, cell in enumerate(cells):
                                        txt = cell.inner_text().strip()
                                        # 如果单元格文本包含关键词 (模糊匹配)
                                        if kw in txt:
                                            # 返回下一个单元格的内容
                                            if idx + 1 < len(cells):
                                                val = cells[idx+1].inner_text().strip()
                                                if val: return val
                            except Exception:
                                pass
                        return ""

                    # 提取关键信息
                    # 注意：Screenshot 显示标签如 "产品名称中文"，所以关键词用 "产品名称" 即可匹配
                    p_name = safe_get_text(["产品名称中文", "产品名称"])

                    # 失败处理：如果连名字都取不到，说明大概率选择器挂了或者页面结构不对
                    if not p_name:
                        print(f"警告：无法提取产品名称！保存调试信息...")
                        timestamp = int(time.time())
                        # 保存截图
                        s_path = f"{screenshot_dir}/error_{page_num}_{i}_{timestamp}.png"
                        detail_page.screenshot(path=s_path)
                        # 保存HTML
                        h_path = f"{screenshot_dir}/error_{page_num}_{i}_{timestamp}.html"
                        try:
                            with open(h_path, "w", encoding="utf-8") as f:
                                f.write(detail_page.content())
                        except:
                            pass
                        print(f"  已保存截图: {s_path}")

                    ent_name = safe_get_text(["注册人中文", "备案人中文", "企业名称", "注册人名称"])
                    reg_no = safe_get_text(["注册证号", "备案编号", "批准文号"])
                    app_date = safe_get_text(["批准日期", "备案日期", "发证日期"])
                    valid_date = safe_get_text(["有效期至", "过期日期"])

                    # --- 提取执行标准 (配方/全成分) ---
                    formula_text = "无"
                    try:
                        # 策略：找到包含“标准”、“配方”的行，点击里面的“查看”
                        target_row_keywords = ["产品执行的标准", "技术要求", "配方", "成分"]
                        found_btn = False

                        for kw in target_row_keywords:
                            row = detail_page.locator(f"tr:has-text('{kw}')").first
                            if row.count() > 0:
                                # 找“查看”
                                btn = row.locator("text=查看").first
                                if btn.count() > 0:
                                    print(f"  发现'{kw}'查看按钮，点击...")
                                    btn.click()
                                    found_btn = True
                                    break

                        if found_btn:
                            # 等待弹窗 (el-dialog)
                            dialog = detail_page.locator(".el-dialog__body").last
                            try:
                                dialog.wait_for(state="visible", timeout=5000)
                                formula_text = dialog.inner_text().strip().replace("\n", " ")
                                # 关闭弹窗：按 ESC 最稳妥
                                detail_page.keyboard.press("Escape")
                                # 等待关闭
                                dialog.wait_for(state="hidden", timeout=3000)
                            except:
                                formula_text = "弹窗读取超时或失败"
                        else:
                            formula_text = "无查看按钮"

                    except Exception as e:
                        formula_text = f"标准提取出错: {e}"

                    print(f"  > 抓取成功: {p_name} | {ent_name}")

                    # 写入 CSV
                    new_row = {
                        "产品名称": p_name,
                        "企业名称": ent_name,
                        "注册证号": reg_no,
                        "批准日期": app_date,
                        "有效期至": valid_date,
                        "状态": status,
                        "产品执行标准全文": formula_text
                    }
                    # Append mode
                    df = pd.DataFrame([new_row])
                    df.to_csv(output_file, mode='a', header=False, index=False, encoding='utf-8-sig')

                    # 关闭详情页
                    if detail_page != page:
                        detail_page.close()
                    else:
                        if page.url != url:
                            page.go_back()

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
