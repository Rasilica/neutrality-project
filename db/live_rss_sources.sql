BEGIN;

UPDATE news_sources
SET name = 'SBS 뉴스 최신',
    rss_url = 'https://news.sbs.co.kr/news/newsflashRssFeed.do?plink=RSSREADER',
    bias_label = 'center'
WHERE name = '연합뉴스(Naver)'
   OR rss_url = 'https://rss.naver.com/main/rss.nhn?oid=001';

UPDATE news_sources
SET name = 'SBS 뉴스 정치',
    rss_url = 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=01&plink=RSSREADER',
    bias_label = 'center'
WHERE name = '경향신문(Naver)'
   OR rss_url = 'https://rss.naver.com/main/rss.nhn?oid=032';

UPDATE news_sources
SET name = 'SBS 뉴스 사회',
    rss_url = 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=03&plink=RSSREADER',
    bias_label = 'center'
WHERE name = '조선일보(Naver)'
   OR rss_url = 'https://rss.naver.com/main/rss.nhn?oid=023';

UPDATE news_sources
SET name = 'SBS 뉴스 경제',
    rss_url = 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=02&plink=RSSREADER',
    bias_label = 'center'
WHERE name = '테스트-네이버직접입력'
   OR name = 'JTBC 뉴스 속보'
   OR rss_url = 'https://news.naver.com';

INSERT INTO news_sources (name, rss_url, bias_label)
VALUES
    ('SBS 뉴스 최신', 'https://news.sbs.co.kr/news/newsflashRssFeed.do?plink=RSSREADER', 'center'),
    ('SBS 뉴스 정치', 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=01&plink=RSSREADER', 'center'),
    ('SBS 뉴스 사회', 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=03&plink=RSSREADER', 'center'),
    ('SBS 뉴스 경제', 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=02&plink=RSSREADER', 'center')
ON CONFLICT (rss_url) DO UPDATE
SET name = EXCLUDED.name,
    bias_label = EXCLUDED.bias_label;

COMMIT;
