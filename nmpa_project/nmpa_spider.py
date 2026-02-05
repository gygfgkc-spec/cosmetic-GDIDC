import time
import pandas as pd
from playwright.sync_api import sync_playwright
import os
import shutil

def run():
    # 1. 准备工作：创建截图目录（用于调试），初始化CSV文件
    screenshot_dir = "debug_screenshots"
    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)

    # 清理旧的截图，防止占用过多空间 (可选)
    # if os.path.exists(screenshot_dir): shutil.rmtree(screenshot_dir); os.makedirs(screenshot_dir)

    output_file = "guangdong_cosmetics.csv"
    # 如果文件不存在，写入表头
    if not os.path.exists(output_file):
        df = pd.DataFrame(columns=["产品名称", "企业名称", "注册证号", "批准日期", "状态", "产品执行标准全文"])
        df.to_csv(output_file, index=False, encoding='utf-8-sig')

    # 2. 启动 Playwright
    with sync_playwright() as p:
        print("正在启动浏览器...")
        # headless=False 方便用户观察
        browser = p.chromium.launch(headless=False, slow_mo=1000, args=['--start-maximized'])

        # 使用特定分辨率，模拟桌面环境
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

        # 尝试点击“广东省”
        # 策略：先尝试点击统计地图，如果不行，找侧边栏或搜索条件的“广东”
        print("正在尝试筛选 '广东省'...")
        try:
            # 这里的 selector 需要根据实际页面调整。根据旧代码逻辑，我们假设有一个文本为“广东”的可点击元素。
            # 为了更稳健，我们使用模糊匹配，并尝试多种选择器
            guangdong_btn = page.locator("text=广东").first
            if guangdong_btn.count() > 0:
                 # 监听新页面（有时候点击省份会弹新窗口）
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
                # 如果用户手动点击产生了新窗口，尝试捕获
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

        # 确保页面加载
        page.wait_for_load_state("domcontentloaded")

        while True:
            print(f"\n>>> 正在处理第 {page_num} 页 <<<")

            # 等待表格加载
            try:
                page.wait_for_selector("tr", timeout=10000)
            except:
                print("等待表格行超时，可能页面加载慢或已无数据。")

            # 抓取表格行
            # NMPA 网站通常使用 ElementUI，表格行是 tr.el-table__row
            rows = page.locator("tr.el-table__row").all()
            if not rows:
                print("未找到 el-table__row，尝试通用 tr...")
                rows = page.locator("tr").all()

            print(f"本页共检测到 {len(rows)} 行数据。")

            # 调试：打印前两行的文本，帮助判断“字符无法识别”的问题
            if len(rows) > 0:
                print(f"DEBUG - 第一行文本预览: {rows[0].inner_text().replace('\n', ' ')[:100]}")

            processed_count = 0

            for i, row in enumerate(rows):
                try:
                    row_text = row.inner_text()

                    # 跳过表头
                    if "产品名称" in row_text and "注册人" in row_text:
                        continue

                    # 提取状态（假设状态在某一列，或者就在文本里）
                    # 常见的状态词：当前批件, 历史批件, 注销, 撤销
                    status = "未知"
                    if "当前批件" in row_text:
                        status = "当前批件"
                    elif "历史" in row_text or "过期" in row_text:
                        status = "历史批件"
                    elif "注销" in row_text:
                        status = "注销"

                    # 筛选逻辑：只保留当前批件
                    if status != "当前批件":
                        # print(f"第 {i+1} 行状态为 '{status}'，跳过。")
                        continue

                    # 找到“详情”按钮
                    # 尝试多种定位方式
                    detail_btn = row.locator("text=详情").first
                    if detail_btn.count() == 0:
                        detail_btn = row.locator("button").last # 有时详情是最后一个按钮

                    if detail_btn.count() == 0:
                        print(f"第 {i+1} 行未找到详情按钮。")
                        continue

                    print(f"正在抓取第 {i+1} 行详情...")

                    # 点击详情，处理弹窗或新标签页
                    try:
                        with context.expect_page(timeout=5000) as detail_page_info:
                            detail_btn.click()
                        detail_page = detail_page_info.value
                    except:
                        # 可能是当前页面的模态框(Dialog)
                        # 如果没有新页面，我们假设是在当前页打开了 Dialog
                        # 这种情况代码处理起来比较复杂，暂时假设是新页面（根据经验 NMPA 多是新页面）
                        print("未检测到新窗口，尝试在当前页面查找弹窗...")
                        detail_page = page
                        # 如果是弹窗，通常需要等待弹窗可见
                        page.wait_for_selector(".el-dialog, .modal", timeout=3000)

                    detail_page.wait_for_load_state("domcontentloaded")
                    detail_page.wait_for_timeout(2000) # 稍作等待确保渲染

                    # --- 详情页数据提取函数 ---
                    def safe_get_text(label):
                        """
                        尝试多种策略提取字段值
                        """
                        try:
                            # 策略 1: 经典的表格结构 <td>Label</td><td>Value</td>
                            # 使用 XPath 查找包含 Label 文本的单元格，然后找它后面的第一个单元格
                            # normalize-space() 用于忽略空格差异
                            xpath_1 = f"//td[contains(text(), '{label}')]/following-sibling::td[1]"
                            if detail_page.locator(xpath_1).count() > 0:
                                return detail_page.locator(xpath_1).first.inner_text().strip()

                            # 策略 2: 可能是 div 布局 <div>Label</div><div>Value</div>
                            xpath_2 = f"//*[contains(text(), '{label}')]/following-sibling::*[1]"
                            if detail_page.locator(xpath_2).count() > 0:
                                return detail_page.locator(xpath_2).first.inner_text().strip()

                            # 策略 3: 输入框结构 <label>Label</label><input value="Value">
                            # 或者是 Form 表单结构

                            return ""
                        except:
                            return ""

                    # 提取关键信息
                    p_name = safe_get_text("产品名称") # 模糊匹配，匹配“产品名称中文”
                    if not p_name: p_name = safe_get_text("产品名称中文")

                    # 如果连产品名称都取不到，说明页面结构完全不匹配，或者加载失败
                    if not p_name:
                        print(f"警告：无法提取产品名称！保存截图用于调试: error_{page_num}_{i}.png")
                        detail_page.screenshot(path=f"{screenshot_dir}/error_{page_num}_{i}.png")
                        # 打印一点源码看一眼
                        # print(detail_page.content()[:500])

                    ent_name = safe_get_text("注册人中文")
                    if not ent_name: ent_name = safe_get_text("备案人中文")
                    if not ent_name: ent_name = safe_get_text("企业名称")

                    reg_no = safe_get_text("注册证号")
                    if not reg_no: reg_no = safe_get_text("备案编号")

                    app_date = safe_get_text("批准日期")

                    # --- 提取执行标准 (配方/全成分) ---
                    formula_text = "无"
                    try:
                        # 寻找“查看”按钮。通常在“产品执行的标准”那一栏。
                        # 我们先找包含“标准”字样的单元格，再在里面找按钮
                        # 或者直接找页面上所有的“查看”按钮

                        # 方法 A: 精确查找
                        view_btn = detail_page.locator("//td[contains(text(), '标准')]//following-sibling::td//span[contains(text(), '查看')]").first
                        if view_btn.count() == 0:
                            view_btn = detail_page.locator("text=查看").first

                        if view_btn.count() > 0:
                            print("  发现'查看'按钮，点击获取标准...")
                            view_btn.click()

                            # 等待标准弹窗
                            # 这里假设是 ElementUI 的 Dialog
                            dialog_body = detail_page.locator(".el-dialog__body").last
                            try:
                                dialog_body.wait_for(state="visible", timeout=5000)
                                formula_text = dialog_body.inner_text().replace("\n", " ")
                                # 如果内容太长，截取一下？不用，全部保存。

                                # 关闭弹窗（虽然直接关闭页面也可以，但为了保险）
                                # close_btn = detail_page.locator(".el-dialog__headerbtn").last
                                # if close_btn.count() > 0: close_btn.click()
                            except:
                                formula_text = "点击查看后未读取到弹窗内容"
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
                        "状态": status,
                        "产品执行标准全文": formula_text
                    }
                    df = pd.DataFrame([new_row])
                    df.to_csv(output_file, mode='a', header=False, index=False, encoding='utf-8-sig')

                    # 关闭详情页（如果是新窗口）
                    if detail_page != page:
                        detail_page.close()
                    else:
                        # 如果是单页应用的面包屑返回，或者弹窗关闭
                        # 这里简单处理：如果是当前页，可能需要回退？
                        # 根据 NMPA 习惯，通常是新窗口。如果不是，这里需要 go_back()
                        if page.url != url: # 如果 URL 变了
                            page.go_back()

                    processed_count += 1

                except Exception as e:
                    print(f"行处理未知错误: {e}")

            if processed_count == 0:
                print("本页没有采集到有效数据（可能是全是历史批件或解析失败）。")

            # 翻页逻辑
            print("尝试翻页...")
            try:
                # 查找下一页按钮
                # ElementUI: <button class="btn-next">
                next_btn = page.locator("button.btn-next").first

                if next_btn.count() > 0:
                    # 检查是否禁用
                    if next_btn.get_attribute("disabled") is not None:
                        print("已到达最后一页。")
                        break

                    next_btn.click()
                    page_num += 1
                    page.wait_for_timeout(3000) # 等待新页加载
                else:
                    # 尝试找文字 ">"
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
