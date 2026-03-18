package com.example.Kcsj.common;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ScriptUtils;

import javax.sql.DataSource;
import java.sql.Connection;

@Configuration
public class SchemaOptimizeRunner {
    private static final Logger log = LoggerFactory.getLogger(SchemaOptimizeRunner.class);

    @Bean
    @ConditionalOnProperty(name = "app.db.optimize-schema.enabled", havingValue = "true")
    public CommandLineRunner optimizeSchemaOnStartup(DataSource dataSource) {
        return args -> {
            ClassPathResource script = new ClassPathResource("db/optimize_student_behavior_schema.sql");
            if (!script.exists()) {
                log.warn("schema optimization script not found: {}", script.getPath());
                return;
            }

            try (Connection conn = dataSource.getConnection()) {
                ScriptUtils.executeSqlScript(conn, script);
                log.info("schema optimization script applied: {}", script.getPath());
            } catch (Exception e) {
                // Keep service booting even if optimization SQL fails.
                log.warn("schema optimization skipped due to error: {}", e.getMessage());
            }
        };
    }
}
