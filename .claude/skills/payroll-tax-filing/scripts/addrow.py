# -*- coding: utf-8 -*-
"""간이지급명세서 인별 1행 입력·등록. 사용: python addrow.py <주민번호13> <성명> <지급액> <소득세> <지방세> <귀속연> <귀속월>"""
import sys, time
sys.path.insert(0, '.')
from edlib import attach
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoAlertPresentException

rrn, name, gross, itax, ltax, yr, mm = sys.argv[1:8]
d = attach(); P = 'mf_txppWframe_wfDetailBrkd_'


def alerts(n=4):
    for _ in range(n):
        try:
            a = d.switch_to.alert
            print('ALERT:', a.text[:100]); a.accept(); time.sleep(2)
        except NoAlertPresentException:
            time.sleep(1)


# 주민번호 → 확인
e = d.find_element(By.ID, P + 'edtIeNo1')
e.clear(); e.send_keys(rrn); time.sleep(1)
d.find_element(By.ID, P + 'btnIeNoChk').click(); time.sleep(4); alerts(2)

# 업종 940600 자문/고문
d.find_element(By.ID, P + 'btnBsicTfbCd').click(); time.sleep(5)
row = [r for r in d.find_elements(By.XPATH, "//tr[contains(.,'940600')]") if r.is_displayed()][0]
btn = [x for x in row.find_elements(By.XPATH, './/button|.//input|.//a') if x.is_displayed()][-1]
d.execute_script('arguments[0].click();', btn); time.sleep(3)
# 업종 레이어가 남아 다음 클릭을 가로막으므로 명시적으로 닫는다
for t in ('UTECMAAA06_wframe_trigger2', 'UTECMAAA06_wframe_trigger6'):
    try:
        x = d.find_element(By.ID, P + t)
        if x.is_displayed():
            d.execute_script('arguments[0].click();', x); time.sleep(2)
    except Exception:
        pass

# 성명 (업종 레이어가 폼을 덮어쓰므로 레이어를 닫은 뒤에 넣는다)
n = d.find_element(By.ID, P + 'edtIeNm'); n.clear(); n.send_keys(name)
d.execute_script("arguments[0].dispatchEvent(new Event('change',{bubbles:true}));arguments[0].blur();", n)
time.sleep(1)

# 귀속연월
Select(d.find_element(By.ID, P + 'attrYr_A0162')).select_by_visible_text(yr); time.sleep(1)
Select(d.find_element(By.ID, P + 'cmbAttrMm')).select_by_visible_text(mm); time.sleep(1)


def setv(i, v):
    x = d.find_element(By.ID, P + i); x.clear(); x.send_keys(v)
    d.execute_script("arguments[0].dispatchEvent(new Event('change',{bubbles:true}));arguments[0].blur();", x)
    time.sleep(1.5)


setv('edtTotaPymnAmt', gross); setv('edtIncTxamt', itax); setv('edtLinTxamt', ltax)

print('--- 입력 확인 ---')
for i in ['edtIeNm', 'edtBsicTfbNm', 'edtTotaPymnAmt', 'edtTxrte', 'edtIncTxamt', 'edtLinTxamt', 'edtTotTxamt']:
    print(i, d.find_element(By.ID, P + i).get_attribute('value'))

# 등록 (버튼이 헤더에 가리므로 스크롤 후 네이티브 클릭)
b = d.find_element(By.ID, P + 'btnAddRow')
d.execute_script("arguments[0].scrollIntoView({block:'center'});", b); time.sleep(1)
b.click(); time.sleep(3); alerts(3)

# 등록 직후 행이 '선택' 상태로 남으면 다음 입력이 수정으로 들어간다 → 폼 리셋
c = d.find_element(By.ID, P + 'btnClearIncBrkd')
d.execute_script("arguments[0].scrollIntoView({block:'center'});", c); time.sleep(1)
c.click(); time.sleep(2); alerts(2)
t = d.find_element(By.TAG_NAME, 'body').text
j = t.find('총 입력건수'); print(t[j:j + 70])
