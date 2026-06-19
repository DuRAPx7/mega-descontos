# Mega Descontos

Site para catalogar ofertas de afiliado por loja e categoria.

## Como testar

Abra `iniciar_site.bat`. Ele inicia o servidor local e abre:

`http://127.0.0.1:8000`

O site, login e painel administrativo possuem botao de tema claro/escuro. A
preferencia fica salva no navegador do visitante.

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

### Programas de afiliado

O bot ja esta preparado para estas variaveis de ambiente:

```text
AMAZON_ASSOCIATE_TAG=sua_tag_amazon
MERCADOLIVRE_AFFILIATE_ID=seu_id_mercado_livre
MERCADOLIVRE_ACCESS_TOKEN=seu_token_api_mercado_livre
MAGALU_PARTNER_ID=seu_id_magalu
SHOPEE_AFFILIATE_ID=seu_id_shopee
ALIEXPRESS_AFFILIATE_ID=seu_id_aliexpress
ADMITAD_SUBID=seu_subid_admitad
```

Para teste local, voce tambem pode copiar `config/affiliate.example.json` para
`config/affiliate.json` e preencher seus dados. Esse arquivo fica ignorado pelo
Git para nao publicar suas credenciais.

`bot/real_sources.json` ja traz buscas reais do Mercado Livre. Para publicar
ofertas reais dessa fonte, configure `MERCADOLIVRE_ACCESS_TOKEN` se a API
responder 403 no ambiente de hospedagem.

`bot/source_feeds.json` aceita feeds/API JSON autorizados de Amazon, Shopee,
Magalu, AliExpress ou Admitad. Basta mapear os campos `title`, `url`,
`affiliateUrl`, `oldPrice`, `currentPrice`, `image` e `expiresAt`.

## Publicar ofertas reais

O site nao publica mais links, fotos ou produtos de exemplo. Uma oferta precisa
ter preco atual menor que o antigo, imagem oficial HTTPS e uma URL de produto
gerada pelo programa de afiliados.

O primeiro fluxo disponivel e:

1. Abra o produto dentro do painel do programa de afiliados.
2. Gere o link de divulgacao oferecido pela propria plataforma.
3. No Admin do Mega Descontos, informe titulo, precos e a imagem oficial.
4. Cole o link gerado em `Link de afiliado` e salve.
5. Use `Abrir link` para conferir o destino antes de divulgar.

O bot tambem aceita `affiliateUrl` diretamente em
`bot/produtos_monitorados.json` ou no `fieldMap` dos feeds autorizados. A Amazon
pode receber a tag configurada por `AMAZON_ASSOCIATE_TAG`. Para as outras lojas,
use a URL completa gerada pela plataforma, pois apenas acrescentar um parametro
generico nao garante o rastreamento da comissao.

### Automacao de ofertas

Existem dois fluxos seguros:

- links `meli.la`: o bot monitora automaticamente titulo, imagem e precos dos
  links gerados no painel de afiliados do Mercado Livre;
- feed afiliado: o bot descobre novos produtos sozinho em feeds JSON, XML/YML
  ou CSV e publica somente itens que ja tragam o deeplink de comissao.

Para ativar o feed da Admitad, obtenha a URL privada do feed de produtos dentro
da sua conta e adicione no Render:

```text
ADMITAD_PRODUCT_FEED_URL=https://endereco-privado-do-seu-feed
```

Nao coloque essa URL no GitHub, pois ela pode conter identificadores ou tokens.
O bot consulta as fontes ao iniciar e depois a cada 10 minutos. Produtos que
somem do feed, ficam sem desconto ou deixam de responder sao retirados do site.

## Publicar online

O projeto ja esta preparado para hospedagem Python com:

- `server.py`
- `requirements.txt`
- `Procfile`
- `render.yaml`

No Render, crie um Web Service apontando para este repositorio e configure:

```text
Build Command: pip install -r requirements.txt
Start Command: python server.py
```

Variaveis de ambiente obrigatorias:

```text
HOST=0.0.0.0
ADMIN_USERNAME=seu_usuario
ADMIN_PASSWORD=sua_senha_forte
DATABASE_URL=postgresql://usuario:senha@servidor:5432/banco
```

Nao use `admin/admin123` em producao.

## Banco de dados persistente

O site usa duas modalidades automaticamente:

- sem `DATABASE_URL`: SQLite local em `data/mega_descontos.db`, ideal para testes;
- com `DATABASE_URL`: PostgreSQL persistente, indicado para o site publicado.

Para ativar em producao:

1. Crie um banco PostgreSQL no Render ou em outro provedor.
2. Copie a URL de conexao fornecida pelo banco.
3. No Web Service do Render, abra `Environment`.
4. Adicione `DATABASE_URL` com a URL completa, sem aspas.
5. Altere o Build Command para `pip install -r requirements.txt`.
6. Salve e execute um novo deploy.

Na primeira conexao com um banco vazio, as ofertas de `data/offers_db.json`
sao importadas automaticamente. Essa migracao acontece uma unica vez. Depois
disso, alteracoes do admin, publicacoes do bot e remocoes de ofertas expiradas
sao gravadas diretamente no banco.

Acesse `/healthz` para conferir o armazenamento ativo. Em producao, o retorno
correto deve conter `"storage": "postgresql"` e `"persistent": true`.

Nunca publique a `DATABASE_URL` em arquivos do Git ou em capturas de tela.
