import React, { useState, useEffect, useRef } from 'react';
import { Client } from '@stomp/stompjs';
import SockJS from 'sockjs-client';
import axios from 'axios';
import { MessageSquare, Globe, Settings as SettingsIcon, LogOut, Search, Send, Moon, Sun } from 'lucide-react';
import './Chat.css';
import Settings from './Settings';

function Chat({ currentUser, onLogout, onUpdateUser, theme, toggleTheme }) {
  const [conversations, setConversations] = useState({});
  const [messageInput, setMessageInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [activeChat, setActiveChat] = useState(null);
  const [connected, setConnected] = useState(false);
  const stompClient = useRef(null);
  const messagesEndRef = useRef(null);
  const activeChatRef = useRef(null);
  const [unreadUsers, setUnreadUsers] = useState({});
  const [knownUsers, setKnownUsers] = useState({});
  const [showSettings, setShowSettings] = useState(false);
  // Derive messages for active chat
  const messages = activeChat ? (conversations[activeChat.username] || []) : [];

  // Connect to WebSocket on mount
  useEffect(() => {
    const socket = new SockJS('http://localhost:8080/ws');
    const client = new Client({
      webSocketFactory: () => socket,
      connectHeaders: {
        login: currentUser.username,
        passcode: 'password',
      },
      onConnect: () => {
        setConnected(true);
        client.subscribe(
          `/topic/messages/${currentUser.username}`,
          (message) => {
            const received = JSON.parse(message.body);
            const otherUser = received.sender === currentUser.username
              ? activeChatRef.current?.username
              : received.sender;

            if (otherUser) {
              setConversations(prev => {
                const existing = prev[otherUser] || [];
                const messageId = received.messageId;

                // If this is a translation update (pending=false), replace the pending entry
                if (messageId && received.pending === 'false') {
                  const idx = existing.findIndex(m => m.messageId === messageId);
                  if (idx !== -1) {
                    const updated = [...existing];
                    updated[idx] = received;
                    return { ...prev, [otherUser]: updated };
                  }
                }

                // If this is our own sent message (sender echo), replace optimistic placeholder
                if (received.sender === currentUser.username) {
                  const pendingIdx = [...existing].reverse()
                    .findIndex(m => m.pending === true && m.original === received.original);
                  if (pendingIdx !== -1) {
                    const realIdx = existing.length - 1 - pendingIdx;
                    const updated = [...existing];
                    updated[realIdx] = received;
                    return { ...prev, [otherUser]: updated };
                  }
                }

                // New message — append it
                return { ...prev, [otherUser]: [...existing, received] };
              });
            }

            // Track incoming senders and mark unread
            if (received.sender !== currentUser.username) {
              setKnownUsers(prev => ({
                ...prev,
                [received.sender]: { username: received.sender }
              }));
              if (activeChatRef.current?.username !== received.sender) {
                setUnreadUsers(prev => ({
                  ...prev,
                  [received.sender]: (prev[received.sender] || 0) + 1
                }));
              }
            }
          }
        );
      },
      onDisconnect: () => setConnected(false),
    });

    client.activate();
    stompClient.current = client;

    return () => client.deactivate();
  }, [currentUser]);

  // Auto scroll to bottom on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversations, activeChat]);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    try {
      const res = await axios.get(
        `http://localhost:8080/api/users/search?query=${searchQuery}`
      );
      setSearchResults(res.data.filter(u => u.username !== currentUser.username));
    } catch (err) {
      console.error('Search failed', err);
    }
  };

  const openChat = (user) => {
    setActiveChat(user);
    activeChatRef.current = user;
    setSearchResults([]);
    setSearchQuery('');
    setUnreadUsers(prev => ({ ...prev, [user.username]: 0 }));
  };

  const sendMessage = () => {
    if (!messageInput.trim() || !activeChat || !connected) return;

    const optimisticMsg = {
      sender: currentUser.username,
      original: messageInput,
      translated: messageInput,
      timestamp: new Date().toISOString(),
      pending: true,
    };

    // Immediately show the message in the UI (optimistic update)
    setConversations(prev => ({
      ...prev,
      [activeChat.username]: [...(prev[activeChat.username] || []), optimisticMsg],
    }));

    stompClient.current.publish({
      destination: '/app/chat.send',
      body: JSON.stringify({
        sender: currentUser.username,
        receiver: activeChat.username,
        text: messageInput,
      }),
    });
    setMessageInput('');
  };

  return (
    <div className="chat-container">

      {/* Sidebar */}
      <div className="sidebar">
        <div className="sidebar-header">
          <div className="user-info" onClick={() => setShowSettings(true)} style={{ cursor: 'pointer' }}>
            {currentUser.profilePhotoUrl ? (
              <img src={currentUser.profilePhotoUrl} alt="profile" className="avatar-img" />
            ) : (
              <div className="avatar">{currentUser.username[0].toUpperCase()}</div>
            )}
            <div>
              <div className="username">{currentUser.username}</div>
              <div className="language"><Globe size={12} className="inline-icon" /> {currentUser.preferredLanguage}</div>
            </div>
          </div>
          <div className="header-actions">
            <button className="icon-btn" onClick={toggleTheme} title="Toggle Theme">
              {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button className="icon-btn" onClick={() => setShowSettings(true)} title="Settings">
              <SettingsIcon size={18} />
            </button>
            <button className="icon-btn logout-btn" onClick={onLogout} title="Logout">
              <LogOut size={18} />
            </button>
          </div>
        </div>

        <div className="search-area">
          <div className="search-input-wrapper">
            <Search size={16} className="search-icon" />
            <input
              type="text"
              placeholder="Search users..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
            />
          </div>
        </div>

        {searchResults.length > 0 && (
          <div className="search-results">
            {searchResults.map(user => (
              <div
                key={user.id}
                className="search-result-item"
                onClick={() => openChat(user)}
              >
                <div className="avatar small">{user.username[0].toUpperCase()}</div>
                <div>
                  <div className="username">{user.username}</div>
                  <div className="language"><Globe size={12} className="inline-icon" /> {user.preferredLanguage}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {Object.keys(knownUsers).length > 0 && (
          <div className="active-chats">
            {Object.values(knownUsers).map(user => (
              <div
                key={user.username}
                className={`active-chat-item ${activeChat?.username === user.username ? 'selected' : ''} ${unreadUsers[user.username] > 0 ? 'unread' : ''}`}
                onClick={() => openChat(user)}
              >
                <div className="avatar small">{user.username[0].toUpperCase()}</div>
                <div style={{ flex: 1 }}>
                  <div className="username">{user.username}</div>
                </div>
                {unreadUsers[user.username] > 0 && (
                  <div className="unread-badge">{unreadUsers[user.username]}</div>
                )}
              </div>
            ))}
          </div>
        )}

      </div> {/* closes sidebar */}

      {/* Main chat area */}
      <div className="chat-main">
        {!activeChat ? (
          <div className="empty-state">
            <MessageSquare size={56} className="empty-icon-svg" />
            <h2>Select a conversation</h2>
            <p>Messages will be instantly translated to {currentUser.preferredLanguage}</p>
          </div>
        ) : (
          <>
            <div className="chat-header">
              <div className="avatar">{activeChat.username[0].toUpperCase()}</div>
              <div>
                <div className="chat-username">{activeChat.username}</div>
                <div className="chat-language">Receives in {activeChat.preferredLanguage}</div>
              </div>
              <div className={`connection-status ${connected ? 'online' : 'offline'}`}>
                {connected ? '● Connected' : '● Disconnected'}
              </div>
            </div>

            <div className="messages-area">
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`message ${msg.sender === currentUser.username ? 'sent' : 'received'}`}
                >
                  <div className="message-bubble">
                    <div className="message-text">
                      {msg.translated}
                      {msg.pending && <span style={{ opacity: 0.5, marginLeft: '6px', fontSize: '11px' }}>⏳</span>}
                    </div>
                    {msg.original !== msg.translated && (
                      <div className="message-original">Original: {msg.original}</div>
                    )}
                    <div className="message-time">
                      {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : ''}
                    </div>
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            <div className="input-area">
              <input
                type="text"
                placeholder="Type your message..."
                value={messageInput}
                onChange={e => setMessageInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && sendMessage()}
              />
              <button
                onClick={sendMessage}
                disabled={!connected || !messageInput.trim()}
                className="send-btn"
                title="Send Message"
              >
                <Send size={18} />
              </button>
            </div>
          </>
        )}
      </div> {/* closes chat-main */}
      {showSettings && (
        <Settings
          currentUser={currentUser}
          onClose={() => setShowSettings(false)}
          onUpdate={(updatedUser) => {
            onUpdateUser(updatedUser);
            setShowSettings(false);
          }}
        />
      )}
    </div> // closes chat-container
  );
}

export default Chat;