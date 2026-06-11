package com.jinro.apiserver.dto;

import com.jinro.apiserver.domain.Article;
import lombok.Getter;

import java.time.ZonedDateTime;
import java.util.List;
import java.util.stream.Collectors;

@Getter
public class ArticleResponseDto {
    private final Long id;
    private final String title;
    private final String url;
    private final String sourceName;
    private final ZonedDateTime publishedAt;
    
    // 분석 결과가 있다면 함께 반환 (리스트의 첫 번째 항목 혹은 전체)
    private final List<AnalysisResultDto> analysisResults;

    public ArticleResponseDto(Article article) {
        this(article, true);
    }

    public ArticleResponseDto(Article article, boolean includeAnalysisResults) {
        this.id = article.getId();
        this.title = article.getTitle();
        this.url = article.getUrl();
        this.sourceName = article.getSource() != null ? article.getSource().getName() : null;
        this.publishedAt = article.getPublishedAt();

        this.analysisResults = includeAnalysisResults
                ? article.getAnalysisResults().stream()
                        .map(AnalysisResultDto::new)
                        .collect(Collectors.toList())
                : List.of();
    }
}
