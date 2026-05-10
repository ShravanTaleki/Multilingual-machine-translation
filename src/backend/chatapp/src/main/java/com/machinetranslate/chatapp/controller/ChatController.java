package com.machinetranslate.chatapp.controller;

import com.machinetranslate.chatapp.model.Message;
import com.machinetranslate.chatapp.model.User;
import com.machinetranslate.chatapp.repository.MessageRepository;
import com.machinetranslate.chatapp.repository.UserRepository;
import com.machinetranslate.chatapp.service.TranslationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.PageRequest;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Controller;
import java.util.*;
import java.util.stream.Collectors;

@Slf4j
@Controller
@RequiredArgsConstructor
public class ChatController {

    private final SimpMessagingTemplate messagingTemplate;
    private final UserRepository userRepository;
    private final MessageRepository messageRepository;
    private final TranslationService translationService;

    @MessageMapping("/chat.send")
    public void sendMessage(@Payload Map<String, String> payload) {
        String senderUsername   = payload.get("sender");
        String receiverUsername = payload.get("receiver");
        String text             = payload.get("text");

        User sender   = userRepository.findByUsername(senderUsername)
                .orElseThrow(() -> new RuntimeException("Sender not found"));
        User receiver = userRepository.findByUsername(receiverUsername)
                .orElseThrow(() -> new RuntimeException("Receiver not found"));

        // ── Phase 1: Instant delivery ─────────────────────────────────────
        // Save with original text immediately so the message is persisted
        Message message = new Message();
        message.setSender(sender);
        message.setReceiver(receiver);
        message.setOriginalText(text);
        message.setTranslatedText(text); // temporary — will be updated after AI
        messageRepository.save(message);

        // Broadcast immediately to sender (always sees own original text)
        Map<String, String> senderPayload = new HashMap<>();
        senderPayload.put("sender", senderUsername);
        senderPayload.put("original", text);
        senderPayload.put("translated", text);
        senderPayload.put("timestamp", message.getTimestamp().toString());
        senderPayload.put("messageId", message.getId().toString());
        messagingTemplate.convertAndSend("/topic/messages/" + senderUsername, senderPayload);

        // Broadcast immediately to receiver with original text (⏳ pending)
        Map<String, String> pendingPayload = new HashMap<>();
        pendingPayload.put("sender", senderUsername);
        pendingPayload.put("original", text);
        pendingPayload.put("translated", text);  // show original until AI finishes
        pendingPayload.put("timestamp", message.getTimestamp().toString());
        pendingPayload.put("messageId", message.getId().toString());
        pendingPayload.put("pending", "true");
        messagingTemplate.convertAndSend("/topic/messages/" + receiverUsername, pendingPayload);

        // ── Phase 2: Async Translation ────────────────────────────────────
        translateAndUpdate(text, receiver, message, senderUsername, receiverUsername);
    }

    @Async
    public void translateAndUpdate(String text, User receiver, Message message,
                                   String senderUsername, String receiverUsername) {
        try {
            // Fetch recent history for context
            User sender = message.getSender();
            List<Message> recentMessages = messageRepository
                    .findRecentMessages(sender, receiver, PageRequest.of(0, 5));
            List<Message> chronological = new ArrayList<>(recentMessages);
            Collections.reverse(chronological);

            List<Map<String, String>> history = chronological.stream()
                    .map(m -> {
                        Map<String, String> entry = new HashMap<>();
                        entry.put("speaker", m.getSender().getUsername());
                        entry.put("text", m.getOriginalText());
                        return entry;
                    })
                    .collect(Collectors.toList());

            String translated = translationService.translate(
                    text,
                    receiver.getPreferredLanguage(),
                    history
            );

            // Update the saved message with the real translation
            message.setTranslatedText(translated);
            messageRepository.save(message);

            // Push the translated update to receiver
            Map<String, String> translatedPayload = new HashMap<>();
            translatedPayload.put("sender", senderUsername);
            translatedPayload.put("original", text);
            translatedPayload.put("translated", translated);
            translatedPayload.put("timestamp", message.getTimestamp().toString());
            translatedPayload.put("messageId", message.getId().toString());
            translatedPayload.put("pending", "false");
            messagingTemplate.convertAndSend("/topic/messages/" + receiverUsername, translatedPayload);

        } catch (Exception e) {
            log.error("[ChatController] Async translation failed: {}", e.getMessage());
        }
    }
}

