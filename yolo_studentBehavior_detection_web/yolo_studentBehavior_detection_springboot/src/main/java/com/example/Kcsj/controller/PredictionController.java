package com.example.Kcsj.controller;

import com.alibaba.fastjson.JSONObject;
import com.example.Kcsj.common.Result;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;

@RestController
@ConditionalOnProperty(name = "app.db.enabled", havingValue = "true")
@RequestMapping("/flask")
public class PredictionController {

    @Value("${app.flask.base-url:http://127.0.0.1:5000}")
    private String flaskBaseUrl;

    @Value("${app.flask.predict-path:/predictImg}")
    private String flaskPredictPath;

    @Value("${app.flask.file-names-path:/file_names}")
    private String flaskFileNamesPath;

    private final RestTemplate restTemplate = new RestTemplate();

    public static class PredictRequest {
        private String startTime;
        private String weight;
        private String username;
        private String inputImg;
        private String kind;
        private String conf;

        public String getUsername() {
            return username;
        }

        public void setUsername(String username) {
            this.username = username;
        }

        public String getStartTime() {
            return startTime;
        }

        public void setStartTime(String startTime) {
            this.startTime = startTime;
        }

        public String getWeight() {
            return weight;
        }

        public void setWeight(String weight) {
            this.weight = weight;
        }

        public String getInputImg() {
            return inputImg;
        }

        public void setInputImg(String inputImg) {
            this.inputImg = inputImg;
        }

        public String getConf() {
            return conf;
        }

        public void setConf(String conf) {
            this.conf = conf;
        }

        public String getKind() {
            return kind;
        }

        public void setKind(String kind) {
            this.kind = kind;
        }
    }

    @PostMapping("/predict")
    public Result<?> predict(@RequestBody PredictRequest request) {
        if (request == null || request.getInputImg() == null || request.getInputImg().isEmpty()) {
            return Result.error(-1, "未提供图片链接");
        }
        if (request.getWeight() == null || request.getWeight().isEmpty()) {
            return Result.error(-1, "未提供权重");
        }

        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            HttpEntity<PredictRequest> requestEntity = new HttpEntity<>(request, headers);

            String endpoint = normalize(flaskBaseUrl) + normalizePath(flaskPredictPath);
            String response = restTemplate.postForObject(endpoint, requestEntity, String.class);
            JSONObject body = JSONObject.parseObject(response);

            Integer status = body.getInteger("status");
            Integer code = body.getInteger("code");
            String message = body.getString("message");
            boolean ok = (status != null && status == 200) || (code != null && code == 0);

            if (!ok) {
                return Result.error(-1, message == null ? "Flask predict failed" : message);
            }

            Object payload = body.get("data");
            if (payload == null) {
                payload = body;
            }
            String normalizedPayload = (payload instanceof String) ? (String) payload : JSONObject.toJSONString(payload);
            return Result.success(normalizedPayload);
        } catch (Exception e) {
            return Result.error(-1, "Error: " + e.getMessage());
        }
    }

    @GetMapping("/file_names")
    public Result<?> getFileNames() {
        try {
            String endpoint = normalize(flaskBaseUrl) + normalizePath(flaskFileNamesPath);
            String response = restTemplate.getForObject(endpoint, String.class);
            JSONObject body = JSONObject.parseObject(response);

            Object payload = body.get("data");
            if (payload == null) {
                payload = body;
            }
            String normalizedPayload = (payload instanceof String) ? (String) payload : JSONObject.toJSONString(payload);
            return Result.success(normalizedPayload);
        } catch (Exception e) {
            return Result.error(-1, "Error: " + e.getMessage());
        }
    }

    private String normalize(String baseUrl) {
        if (baseUrl == null || baseUrl.isEmpty()) {
            return "http://127.0.0.1:5000";
        }
        return baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
    }

    private String normalizePath(String path) {
        if (path == null || path.isEmpty()) {
            return "";
        }
        return path.startsWith("/") ? path : ("/" + path);
    }
}
