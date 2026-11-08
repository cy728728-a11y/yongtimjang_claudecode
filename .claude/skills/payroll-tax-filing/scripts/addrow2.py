# -*- coding: utf-8 -*-
"""간이지급명세서 1행 입력·등록 (업종 → 이름/금액 → 주민번호확인 → 등록 순서).
업종 검색 레이어를 열면 폼이 목록의 기존 행으로 되돌아가므로, 업종을 가장 먼저 고른다.
사용: python addrow2.py <주민13> <성명> <지급액> <소득세> <지방세> <귀속연> <귀속월>"""
import sys, time
sys.path.insert(0, '.')
from edlib import attach
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoAlertPresentException

rrn, name, gross, itax, ltax, yr, mm = sys.argv[1:8]
d = attach(); P = 'mf_txppWframe_wfDetailBrkd_'


def alerts(n=3):
    for _ in range(n):
        try:
            a = d.switch_to.alert
            print('A:', a.text[:90]); a.accept(); time.sleep(2)
        except NoAlertPresentException:
            time.sleep(1)


def nclick(i):
    b = d.find_element(By.ID, P + i)
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
    time.sleep(1); b.click(); time.sleep(3)


def setv(i, v):
    x = d.find_element(By.ID, P + i); x.clear(); x.send_keys(v)
    d.execute_script("arguments[0].dispatchEvent(new Event('change',{bubbles:true}));arguments[0].blur();", x)
    time.sleep(1.5)


# 1) 업종 940600 자문/고문 (폼 리로드를 유발하므로 가장 먼저)
d.find_element(By.ID, P + 'btnBsicTfbCd').click(); time.sleep(5)
row = [r for r in d.find_elements(By.XPATH, "//tr[contains(.,'940600')]") if r.is_displayed()][0]
sel = [x for x in row.find_elements(By.XPATH, './/button|.//input|.//a') if x.is_displayed()][-1]
d.execute_script('arguments[0].click();', sel); time.sleep(3)
for t in ('UTECMAAA06_wframe_trigger2', 'UTECMAAA06_wframe_trigger6'):
    try:
        x = d.find_element(By.ID, P + t)
        if x.is_displayed():
            d.execute_script('arguments[0].click();', x); time.sleep(2)
    except Exception:
        pass

# 2) 이름·귀속연월·금액
n = d.find_element(By.ID, P + 'edtIeNm'); n.clear(); n.send_keys(name)
d.execute_script("arguments[0].dispatchEvent(new Event('change',{bubbles:true}));arguments[0].blur();", n)
time.sleep(1)
Select(d.find_element(By.ID, P + 'attrYr_A0162')).select_by_visible_text(yr); time.sleep(1)
Select(d.find_element(By.ID, P + 'cmbAttrMm')).select_by_visible_text(mm); time.sleep(1)
setv('edtTotaPymnAmt', gross); setv('edtIncTxamt', itax); setv('edtLinTxamt', ltax)

# 3) 주민번호 → 확인 (마지막에 해야 수정모드로 안 빠진다)
e = d.find_element(By.ID, P + 'edtIeNo1'); e.clear(); e.send_keys(rrn); time.sleep(1)
d.find_element(By.ID, P + 'btnIeNoChk').click(); time.sleep(4); alerts(2)

print('--- 입력 확인 ---')
for i in ['edtIeNo1', 'edtIeNm', 'edtBsicTfbNm', 'edtTotaPymnAmt', 'edtTxrte', 'edtIncTxamt', 'edtLinTxamt', 'edtTotTxamt']:
    print(i, d.find_element(By.ID, P + i).get_attribute('value'))

nclick('btnAddRow'); alerts()
t = d.find_element(By.TAG_NAME, 'body').text
j = t.find('선택 번호 수정'); print(t[j:j + 320])
