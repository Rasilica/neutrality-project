package com.jinro.apiserver.controller;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.empty;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ActiveProfiles("test")
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
        "app.rate-limit.enabled=false",
        "logging.level.com.jinro.apiserver.logging=ERROR"
})
class ArticleApiIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void setUp() {
        jdbcTemplate.update("DELETE FROM comment_analysis");
        jdbcTemplate.update("DELETE FROM analysis_results");
        jdbcTemplate.update("DELETE FROM articles");
        jdbcTemplate.update("DELETE FROM news_sources");

        jdbcTemplate.update("""
                INSERT INTO news_sources (id, name, rss_url, bias_label, created_at)
                VALUES
                    (100, 'SBS 뉴스 통합테스트', 'https://news.sbs.co.kr/rss.xml', 'center', CURRENT_TIMESTAMP),
                    (101, 'JTBC 뉴스 통합테스트', 'https://fs.jtbc.co.kr/RSS/newsflash.xml', 'center', CURRENT_TIMESTAMP)
                """);
        jdbcTemplate.update("""
                INSERT INTO articles (id, source_id, title, content, url, published_at, created_at)
                VALUES
                    (200, 100, 'SBS 기사 분석과 댓글 분석 모두 성공한 기사', '본문 내용', 'https://news.sbs.co.kr/news/endPage.do?news_id=N1000000200',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (201, 100, 'SBS 기사 분석만 성공한 기사', '본문 내용', 'https://news.sbs.co.kr/news/endPage.do?news_id=N1000000201',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (202, 100, 'SBS 댓글 분석만 성공한 기사', '본문 내용', 'https://news.sbs.co.kr/news/endPage.do?news_id=N1000000202',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (203, 101, 'JTBC 분석 성공했지만 제외할 기사', '본문 내용', 'https://news.jtbc.co.kr/article/article.aspx?news_id=NB12220953',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """);
        jdbcTemplate.update("""
                INSERT INTO analysis_results (
                    id, article_id, model_used, sentiment_score, bias_score, factuality_score, summary, analyzed_at
                )
                VALUES
                    (300, 200, 'gemini-cross-check', 0.12, 0.24, 0.88, '통합 테스트용 분석 요약', CURRENT_TIMESTAMP),
                    (301, 201, 'gemini-cross-check', 0.10, 0.20, 0.80, '기사 분석만 있는 요약', CURRENT_TIMESTAMP),
                    (303, 203, 'gemini-cross-check', 0.10, 0.20, 0.80, 'JTBC 요약', CURRENT_TIMESTAMP)
                """);
        jdbcTemplate.update("""
                INSERT INTO comment_analysis (
                    id, article_id, total_comments, avg_sentiment, positive_ratio, negative_ratio, neutral_ratio,
                    public_opinion, analyzed_at
                )
                VALUES
                    (400, 200, 6, -0.77, 0.0, 1.0, 0.0, 'SBS 댓글 여론 분석 완료', CURRENT_TIMESTAMP),
                    (402, 202, 3, -0.10, 0.2, 0.3, 0.5, '댓글 분석만 완료', CURRENT_TIMESTAMP),
                    (403, 203, 2, 0.10, 0.4, 0.2, 0.4, 'JTBC 댓글 분석 완료', CURRENT_TIMESTAMP)
                """);
    }

    @Test
    void articleListReturnsDocumentedPagedResponse() throws Exception {
        mockMvc.perform(get("/api/v1/articles")
                        .param("page", "0")
                        .param("size", "5")
                        .param("sort", "id,asc"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Content-Type-Options", "nosniff"))
                .andExpect(jsonPath("$.content", hasSize(2)))
                .andExpect(jsonPath("$.content[0].id").value(200))
                .andExpect(jsonPath("$.content[0].title").value("SBS 기사 분석과 댓글 분석 모두 성공한 기사"))
                .andExpect(jsonPath("$.content[1].id").value(201))
                .andExpect(jsonPath("$.content[1].title").value("SBS 기사 분석만 성공한 기사"))
                .andExpect(jsonPath("$.content[0].sourceName").value("SBS 뉴스 통합테스트"))
                .andExpect(jsonPath("$.content[0].analysisResults", empty()))
                .andExpect(jsonPath("$.page.number").value(0))
                .andExpect(jsonPath("$.page.size").value(5))
                .andExpect(jsonPath("$.page.totalElements").value(2));
    }

    @Test
    void articleDetailReturnsArticleWithAnalysisResults() throws Exception {
        mockMvc.perform(get("/api/v1/articles/200"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(200))
                .andExpect(jsonPath("$.url").value("https://news.sbs.co.kr/news/endPage.do?news_id=N1000000200"))
                .andExpect(jsonPath("$.analysisResults", hasSize(1)))
                .andExpect(jsonPath("$.analysisResults[0].modelUsed").value("gemini-cross-check"))
                .andExpect(jsonPath("$.analysisResults[0].sentimentScore").value(0.12))
                .andExpect(jsonPath("$.analysisResults[0].biasScore").value(0.24))
                .andExpect(jsonPath("$.analysisResults[0].factualityScore").value(0.88))
                .andExpect(jsonPath("$.analysisResults[0].summary").value("통합 테스트용 분석 요약"));
    }

    @Test
    void articleAnalysisReturnsAnalysisOnlySubResource() throws Exception {
        mockMvc.perform(get("/api/v1/articles/200/analysis"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].id").value(300))
                .andExpect(jsonPath("$[0].modelUsed").value("gemini-cross-check"));
    }

    @Test
    void missingArticleReturnsDocumentedNotFoundError() throws Exception {
        mockMvc.perform(get("/api/v1/articles/999999"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.error").value("Not Found"))
                .andExpect(jsonPath("$.message").value("존재하지 않는 기사입니다. id=999999"))
                .andExpect(jsonPath("$.path").value("/api/v1/articles/999999"));
    }
}
