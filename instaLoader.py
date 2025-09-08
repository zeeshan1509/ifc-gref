#!/usr/bin/env python3
import os
import sys
import time
import csv
import argparse

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException
)

BASE = "https://www.instagram.com"
LOGIN = f"{BASE}/accounts/login/"
TAG_URL = f"{BASE}/explore/tags/{{tag}}/"

def make_driver(headless: bool = False):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--lang=en-US,en")
    # Selenium Manager will handle the correct driver automatically:
    return webdriver.Chrome(options=opts)

def wait_click_text(driver, text, timeout=6):
    try:
        btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, f"//button[normalize-space()='{text}']"))
        )
        btn.click()
        time.sleep(0.6)
        return True
    except TimeoutException:
        return False

def post_login_cleanup(driver):
    # dismiss cookie & “save login”, “turn on notifications”
    for t in ("Only allow essential cookies", "Allow all cookies", "Accept all"):
        wait_click_text(driver, t, 2)
    for t in ("Not now", "Not Now"):
        wait_click_text(driver, t, 2)

def login(driver, username: str | None, password: str | None):
    driver.get(BASE)
    time.sleep(2)
    # if already logged in, nav elements may exist
    try:
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "nav,[role='navigation']")))
        return
    except TimeoutException:
        pass

    driver.get(LOGIN)
    time.sleep(2)
    if username and password:
        try:
            user_in = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "username")))
            pass_in = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "password")))
            user_in.clear(); user_in.send_keys(username)
            pass_in.clear(); pass_in.send_keys(password); pass_in.send_keys(Keys.ENTER)
            time.sleep(4)
        except TimeoutException:
            print("[error] Could not locate login fields.", file=sys.stderr)
            return
        post_login_cleanup(driver)
    else:
        print("\n[info] No IG_USER/IG_PASS provided. Log in manually in the opened browser.")
        print("      After your feed loads, return to the terminal and press ENTER.")
        input("Press ENTER to continue after manual login… ")
        post_login_cleanup(driver)

def collect_hashtag_post_urls(driver, hashtag: str, limit: int) -> list[str]:
    driver.get(TAG_URL.format(tag=hashtag))
    time.sleep(3)

    try:
        WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.TAG_NAME, "article")))
    except TimeoutException:
        pass

    urls = []
    seen = set()
    last_height = driver.execute_script("return document.body.scrollHeight")
    idle_rounds = 0

    while len(urls) < limit and idle_rounds < 12:
        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/p/'], a[href*='/reel/']")
        for a in anchors:
            href = a.get_attribute("href")
            if href and ("/p/" in href or "/reel/" in href) and href not in seen:
                seen.add(href)
                urls.append(href)
                if len(urls) >= limit:
                    break

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2.2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        idle_rounds = idle_rounds + 1 if new_height == last_height else 0
        last_height = new_height

    return urls[:limit]

def extract_caption(driver, post_url: str) -> str:
    driver.get(post_url)
    time.sleep(2.5)

    # Try common caption locations (IG changes often)
    # Strategy 1: article h1
    try:
        article = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.TAG_NAME, "article")))
        h1s = article.find_elements(By.CSS_SELECTOR, "h1")
        if h1s:
            txt = h1s[0].text.strip()
            if txt:
                return txt
    except TimeoutException:
        pass

    # Strategy 2: og:description meta
    try:
        meta = driver.find_element(By.CSS_SELECTOR, "meta[property='og:description']")
        c = (meta.get_attribute("content") or "").strip()
        if c:
            return c
    except NoSuchElementException:
        pass

    # Strategy 3: longest visible text in article
    try:
        texts = []
        for sel in ["p", "span", "h2", "h3"]:
            for el in driver.find_elements(By.CSS_SELECTOR, f"article {sel}"):
                t = el.text.strip()
                if t and len(t) > 1:
                    texts.append(t)
        texts.sort(key=len, reverse=True)
        if texts:
            return texts[0]
    except WebDriverException:
        pass

    return ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hashtag", "-t", default="flood")
    ap.add_argument("--limit", "-n", type=int, default=100)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--out", "-o", default="csvScrapedData.csv")
    args = ap.parse_args()

    # env creds (optional)
    IG_USER = os.getenv("IG_USER")
    IG_PASS = os.getenv("IG_PASS")

    driver = make_driver(headless=args.headless)

    try:
        login(driver, IG_USER, IG_PASS)

        print(f"[info] Collecting post URLs for #{args.hashtag} …")
        urls = collect_hashtag_post_urls(driver, args.hashtag, args.limit)
        print(f"[info] Found {len(urls)} post URLs. Extracting captions…")

        rows = [["description", "user", "time", "image", "post_url"]]

        for i, u in enumerate(urls, 1):
            try:
                caption = extract_caption(driver, u)

                # (Optional) Try to grab poster handle & time quickly
                try:
                    user_el = driver.find_element(By.CSS_SELECTOR, "header a[role='link']")
                    user = user_el.text.strip()
                except NoSuchElementException:
                    user = ""

                try:
                    time_el = driver.find_element(By.CSS_SELECTOR, "time")
                    ts = time_el.get_attribute("datetime") or ""
                except NoSuchElementException:
                    ts = ""

                try:
                    img_el = driver.find_element(By.CSS_SELECTOR, "article img")
                    img = img_el.get_attribute("src") or ""
                except NoSuchElementException:
                    img = ""

                rows.append([caption, user, ts, img, u])
            except Exception as e:
                print(f"[warn] Failed on {u}: {e}")
            time.sleep(0.6)

        with open(args.out, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            writer.writerows(rows)

        print(f"[done] Saved {len(rows)-1} posts to {args.out}")

    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
