package com.jinro.apiserver.repository;

import com.jinro.apiserver.domain.AnalysisResult;
import com.jinro.apiserver.domain.Article;
import org.springframework.data.jpa.domain.Specification;

import java.util.List;

public final class ArticleSpecifications {

    private ArticleSpecifications() {
    }

    public static Specification<Article> withAnalysisFromHosts(List<String> hosts) {
        return (root, query, criteriaBuilder) -> {
            var hostPredicates = hosts.stream()
                    .map(host -> criteriaBuilder.like(root.get("url"), "https://" + host + "/%"))
                    .toArray(jakarta.persistence.criteria.Predicate[]::new);

            var analysisSubquery = query.subquery(Long.class);
            var analysisRoot = analysisSubquery.from(AnalysisResult.class);
            analysisSubquery.select(analysisRoot.get("id"))
                    .where(criteriaBuilder.equal(analysisRoot.get("article"), root));

            return criteriaBuilder.and(
                    criteriaBuilder.or(hostPredicates),
                    criteriaBuilder.exists(analysisSubquery)
            );
        };
    }
}
