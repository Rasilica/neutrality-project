package com.jinro.apiserver.service;

import com.jinro.apiserver.domain.Article;
import com.jinro.apiserver.dto.AnalysisResultDto;
import com.jinro.apiserver.dto.ArticleResponseDto;
import com.jinro.apiserver.exception.ResourceNotFoundException;
import com.jinro.apiserver.repository.AnalysisResultRepository;
import com.jinro.apiserver.repository.ArticleRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ArticleService {

    private static final String SBS_NEWS_DOMAIN_PATTERN = "%news.sbs.co.kr%";

    private final ArticleRepository articleRepository;
    private final AnalysisResultRepository analysisResultRepository;

    public Page<ArticleResponseDto> getArticles(Pageable pageable) {
        return articleRepository.findSbsArticlesWithArticleAnalysis(SBS_NEWS_DOMAIN_PATTERN, pageable)
                .map(article -> new ArticleResponseDto(article, false));
    }

    public ArticleResponseDto getArticle(Long id) {
        Article article = articleRepository.findWithAnalysisResultsById(id)
                .orElseThrow(() -> new ResourceNotFoundException("존재하지 않는 기사입니다. id=" + id));
        return new ArticleResponseDto(article);
    }

    public List<AnalysisResultDto> getArticleAnalysis(Long id) {
        // 기사 존재 여부 먼저 확인
        articleRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("존재하지 않는 기사입니다. id=" + id));
        
        return analysisResultRepository.findByArticleId(id).stream()
                .map(AnalysisResultDto::new)
                .collect(Collectors.toList());
    }
}
