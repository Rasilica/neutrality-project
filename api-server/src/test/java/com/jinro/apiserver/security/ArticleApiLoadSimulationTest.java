package com.jinro.apiserver.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.stream.IntStream;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

@ActiveProfiles("test")
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
        "app.rate-limit.enabled=false",
        "logging.level.com.jinro.apiserver.logging=ERROR"
})
class ArticleApiLoadSimulationTest {

    private static final int REQUEST_COUNT = 40;
    private static final int CONCURRENCY = 8;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void articleListHandlesConcurrentReadLoad() throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(CONCURRENCY);
        CountDownLatch startSignal = new CountDownLatch(1);

        try {
            List<Future<RequestMetric>> futures = IntStream.range(0, REQUEST_COUNT)
                    .mapToObj(index -> executor.submit(() -> executeArticleListRequest(startSignal)))
                    .toList();

            startSignal.countDown();

            List<RequestMetric> metrics = new ArrayList<>();
            for (Future<RequestMetric> future : futures) {
                metrics.add(future.get());
            }

            long p95Millis = percentile(metrics, 95);
            long maxMillis = metrics.stream()
                    .map(RequestMetric::elapsedMillis)
                    .max(Comparator.naturalOrder())
                    .orElse(0L);

            assertThat(metrics).hasSize(REQUEST_COUNT);
            assertThat(metrics).allMatch(metric -> metric.status() == 200);
            assertThat(p95Millis).isLessThan(2000L);
            assertThat(maxMillis).isLessThan(3000L);
        } finally {
            executor.shutdownNow();
        }
    }

    private RequestMetric executeArticleListRequest(CountDownLatch startSignal) throws Exception {
        startSignal.await();
        long startedAt = System.nanoTime();
        MvcResult result = mockMvc.perform(get("/api/v1/articles").param("size", "5"))
                .andReturn();
        long elapsedMillis = (System.nanoTime() - startedAt) / 1_000_000L;
        return new RequestMetric(result.getResponse().getStatus(), elapsedMillis);
    }

    private long percentile(List<RequestMetric> metrics, int percentile) {
        List<Long> sortedMillis = metrics.stream()
                .map(RequestMetric::elapsedMillis)
                .sorted()
                .toList();
        int index = (int) Math.ceil(percentile / 100.0 * sortedMillis.size()) - 1;
        return sortedMillis.get(Math.max(index, 0));
    }

    private record RequestMetric(int status, long elapsedMillis) {
    }
}
