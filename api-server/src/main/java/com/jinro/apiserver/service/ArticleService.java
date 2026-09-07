package com.jinro.apiserver.service;

import com.jinro.apiserver.domain.Article;
import com.jinro.apiserver.dto.AnalysisResultDto;
import com.jinro.apiserver.dto.ArticleResponseDto;
import com.jinro.apiserver.exception.ResourceNotFoundException;
import com.jinro.apiserver.repository.AnalysisResultRepository;
import com.jinro.apiserver.repository.ArticleRepository;
import com.jinro.apiserver.repository.ArticleSpecifications;
import com.jinro.apiserver.security.ArticleSourceProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.net.URI;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ArticleService {

    private final ArticleRepository articleRepository;
    private final AnalysisResultRepository analysisResultRepository;
    private final ArticleSourceProperties articleSourceProperties;

    public Page<ArticleResponseDto> getArticles(Pageable pageable) {
        return articleRepository.findAll(
                        ArticleSpecifications.withAnalysisFromHosts(articleSourceProperties.getHosts()),
                        pageable
                )
                .map(article -> new ArticleResponseDto(article, false));
    }

    public ArticleResponseDto getArticle(Long id) {
        Article article = articleRepository.findWithAnalysisResultsById(id)
                .orElseThrow(() -> new ResourceNotFoundException("존재하지 않는 기사입니다. id=" + id));
        ensureAllowedSource(article);
        return new ArticleResponseDto(article);
    }

    public List<AnalysisResultDto> getArticleAnalysis(Long id) {
        // 기사 존재 여부 먼저 확인
        Article article = articleRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("존재하지 않는 기사입니다. id=" + id));
        ensureAllowedSource(article);
        
        return analysisResultRepository.findByArticleId(id).stream()
                .map(AnalysisResultDto::new)
                .collect(Collectors.toList());
    }

    private void ensureAllowedSource(Article article) {
        try {
            URI uri = URI.create(article.getUrl());
            boolean allowed = "https".equalsIgnoreCase(uri.getScheme())
                    && uri.getHost() != null
                    && articleSourceProperties.getHosts().stream()
                    .anyMatch(host -> host.equalsIgnoreCase(uri.getHost().replaceFirst("\\.$", "")));
            if (!allowed) {
                throw new ResourceNotFoundException("존재하지 않는 기사입니다. id=" + article.getId());
            }
        } catch (IllegalArgumentException exception) {
            throw new ResourceNotFoundException("존재하지 않는 기사입니다. id=" + article.getId());
        }
    }
}
