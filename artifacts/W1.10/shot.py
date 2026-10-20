import sys
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By

page, out = Path(sys.argv[1]).resolve(), sys.argv[2]
options = webdriver.ChromeOptions()
for flag in ("--headless=new", "--no-sandbox", "--window-size=1440,900"):
    options.add_argument(flag)
driver = webdriver.Chrome(options=options)
driver.get(page.as_uri())
driver.implicitly_wait(10)
driver.execute_script("window.scrollTo(0, 0)")
print(driver.find_element(By.ID, "pathnote").text)
print(driver.find_element(By.CSS_SELECTOR, ".legend").text.replace("\n", " | "))
driver.find_element(By.ID, "plan-map").screenshot(out)
driver.quit()
