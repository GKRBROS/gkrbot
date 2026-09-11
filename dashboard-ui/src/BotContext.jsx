import { createContext, useContext, useEffect, useState } from 'react';
import api from './api';

const BotContext = createContext({ botName: 'Bot' });

export function BotProvider({ children }) {
  const [botName, setBotName] = useState('Bot');

  useEffect(() => {
    api.get('/bot-info')
      .then(res => {
        if (res.data?.bot_name) setBotName(res.data.bot_name);
      })
      .catch(() => {}); // silently fall back to default
  }, []);

  return (
    <BotContext.Provider value={{ botName }}>
      {children}
    </BotContext.Provider>
  );
}

export function useBotName() {
  return useContext(BotContext).botName;
}

export default BotContext;
