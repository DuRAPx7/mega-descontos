# Mega Descontos

Site para catalogar ofertas de afiliado por loja e categoria.

## Como testar

Abra `iniciar_site.bat`. Ele inicia o servidor local e abre:

`http://127.0.0.1:8000`

## Painel administrativo

Abra `http://127.0.0.1:8000/admin.html` para cadastrar, editar, excluir,
restaurar e exportar ofertas.

Login inicial:

```text
Usuario: admin
Senha: admin123
```

Troque esses dados em `config/admin.json`.

Quando aberto pelo servidor local, as alteracoes ficam salvas em
`data/offers_db.json`.

O painel tambem importa arquivos `.json`, incluindo `bot/ofertas_geradas.json`.

## Onde trocar seus links

As ofertas iniciais ficam em `data/offers.js`. Voce tambem pode cadastrar pelo
painel administrativo em `admin.html`.

```js
affiliateUrl: "https://www.amazon.com.br/?tag=SEU-CODIGO-AQUI"
```

## Proximo passo do bot

Edite `bot/produtos_monitorados.json` com os produtos que deseja acompanhar e
execute `rodar_bot.bat`.

O bot gera `bot/ofertas_geradas.json` para conferencia e atualiza
automaticamente `data/offers_db.json`, que e o arquivo lido pelo site.

O servidor tambem executa o bot automaticamente a cada 10 minutos enquanto
`iniciar_site.bat` estiver aberto.

Ofertas com `expiresAt` vencido sao retiradas automaticamente do site.

## Ofertas reais e imagens das lojas

Use `bot/source_feeds.json` para cadastrar feeds ou APIs JSON autorizados.
O bot le os campos de titulo, preco, link, imagem e validade informados pelo
feed. Para Amazon, Shopee, Magalu e Mercado Livre, use APIs oficiais, feeds
de afiliado ou parceiros autorizados; evite raspagem direta de paginas.

Para Amazon, Shopee e outros marketplaces, prefira APIs oficiais, feeds
autorizados ou integracoes de programas de afiliados.

## Publicar online

O projeto ja esta preparado para hospedagem Python com:

- `server.py`
- `requirements.txt`
- `Procfile`
- `render.yaml`

No Render, crie um Web Service apontando para este repositorio e configure:

```text
Build Command: vazio
Start Command: python server.py
```

Variaveis de ambiente obrigatorias:

```text
HOST=0.0.0.0
ADMIN_USERNAME=seu_usuario
ADMIN_PASSWORD=sua_senha_forte
```

Nao use `admin/admin123` em producao.

Observacao: em hospedagens gratuitas, arquivos JSON locais podem ser resetados
em redeploy/restart. Para producao real, o proximo passo recomendado e trocar
`data/offers_db.json` por banco persistente, como SQLite em disco persistente,
PostgreSQL ou outro banco oferecido pela hospedagem.
