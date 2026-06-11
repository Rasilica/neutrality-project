package com.jinro.apiserver.repository;

import com.jinro.apiserver.domain.Article;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface ArticleRepository extends JpaRepository<Article, Long> {

    @Override
    @EntityGraph(attributePaths = {"source"})
    Page<Article> findAll(Pageable pageable);

    @EntityGraph(attributePaths = {"source"})
    @Query("""
            select article
            from Article article
            where article.url like :sourceDomainPattern
              and exists (
                  select analysis.id
                  from AnalysisResult analysis
                  where analysis.article = article
              )
            """)
    Page<Article> findSbsArticlesWithArticleAnalysis(
            @Param("sourceDomainPattern") String sourceDomainPattern,
            Pageable pageable
    );

    @EntityGraph(attributePaths = {"source", "analysisResults"})
    Optional<Article> findWithAnalysisResultsById(Long id);
}
