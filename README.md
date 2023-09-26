# Simples App para usar Rich Presence em bots de música que usam essa [source](https://github.com/zRitsu/MuseHeart-MusicBot).


### Presence Preview:
![](https://cdn.discordapp.com/attachments/554468640942981147/1087128133095915583/rpc_preview.png)

### App Preview:
![](https://cdn.discordapp.com/attachments/554468640942981147/1087135148761428028/image.png)

## Para usar o app você pode usar um dos seguintes métodos abaixo:

---
1 - Usando a versão já compilada pra EXE que está nos [releases](https://github.com/zRitsu/Discord-MusicBot-RPC/releases) (Apenas windows)

2 - Executando o code diretamente seguindo os passos abaixo:

* Baixe o code deste repositório como zip clicando no botão "code" e depois em download zip.
* Extraia o arquivo zip e navegue na pasta até encontrar os arquivos da source.
* Use o comando abaixo para instalar as dependências:
```
python3 -m pip install -r requirements.txt
```
* Agora basta apenas usar o comando abaixo para executar o app:
```
python3 rpc_client.py
```
* Opcional: Caso queira compilar pra EXE você pode clicar 2x no arquivo build.bat (recomendado) ou executar o comando abaixo (após o processo o arquivo vai estar na pasta: builds):
```
pyinstaller rpc_client.py
```
---
### Será necessário ter o link do websocket de onde o bot está rodando para add no App.

* Caso esteja rodando a source de música localmente no pc (e que não tenha alterado qualquer configuração padrão no .env) geralmente o link é esse:
```
ws://localhost/ws
```
* Se seu bot tiver hospedado em algum serviço que forneça acesso http (ex: Repl.it, Heroku etc) o link do app será exibido na página renderizada:

![](https://cdn.discordapp.com/attachments/554468640942981147/1087148423767130112/image.png)

* Adicione o link do websocket na aba Socket Settings.

* Obtenha o token de acesso através do bot usando o comando `/rich_presence` (ou mencionando o bot em uma mensagem: `@bot richpresence`).

* Adicione o token na aba Socket Settings.

Após configurar esses dois itens, basta clicar em "Iniciar Presence".

---

### Caso tenha algum problema, poste uma [issue](https://github.com/zRitsu/Discord-MusicBot-RPC/issues) detalhando o problema.
