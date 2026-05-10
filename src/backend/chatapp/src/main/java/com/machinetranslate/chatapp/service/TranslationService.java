package com.machinetranslate.chatapp.service;


import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class TranslationService {

    @Value("${translator.api.url}")
    private String translatorApiUrl;

    private final RestTemplate restTemplate;

    public String translate(String text, String targetLanguage) {
        return translate(text, targetLanguage, List.of());
    }

    public String translate(String text, String targetLanguage,
                            List<Map<String, String>> history) {
        try {
            log.info("[Translation] Calling {} → target={}, history_size={}",
                    translatorApiUrl, targetLanguage, history.size());

            Map<String, Object> request = new HashMap<>();
            request.put("text", text);
            request.put("target_language", targetLanguage);
            request.put("history", history);

            Map response = restTemplate.postForObject(
                    translatorApiUrl + "/translate",
                    request,
                    Map.class
            );

            String result = (String) response.get("translation");
            log.info("[Translation] ✅ Success: \"{}\" → \"{}\"", text, result);
            return result;

        } catch (Exception e) {
            // Log the real error so it's visible in the console
            log.error("[Translation] ❌ FAILED for text=\"{}\", target=\"{}\". Reason: {}",
                    text, targetLanguage, e.getMessage());
            return text;
        }
    }
}
