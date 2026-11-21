# Local Work Order PDF Extractor

**Extrator local e multilíngue de PDFs de ordens de serviço** · Python · PyMuPDF · Regex

Este projeto demonstra uma abordagem de engenharia de dados para transformar relatórios PDF de ordens de serviço em registros JSON e CSV. O processamento é feito localmente: os PDFs são lidos do disco e não são enviados para APIs, serviços de IA, armazenamento em nuvem ou outros serviços externos pelo código.

> **Portfólio público e privacidade:** este repositório contém somente código genérico, documentação e exemplos sintéticos. Não inclui PDFs operacionais, nomes de clientes, fornecedores, empresas, parques, ativos, números reais de OS, dados de manutenção ou saídas de sistemas corporativos. Os exemplos de teste foram criados exclusivamente para este repositório.

[English summary](#english-summary) · [Privacidade](#privacidade-e-uso-responsavel)

## Visão geral

O extrator foi projetado para lidar com variações comuns entre formulários de ordens de serviço:

- Reconhecimento de rótulos em **inglês, espanhol e português**, com comparação tolerante a acentos, caixa e pontuação.
- Segmentação de documentos em que uma ordem pode continuar em páginas seguintes.
- Extração de campos de identificação, descrição da atividade, alarmes, dados operacionais, classificação de falha e períodos de parada.
- Preservação de linhas textuais de tabelas de mão de obra, materiais e ferramentas quando o texto do PDF não permite inferir com segurança o alinhamento das células.
- Sinalização de campos ou seções ausentes e de valores que precisam de revisão, sem inventar dados nem corrigir automaticamente o conteúdo de origem.
- Processamento incremental por tamanho, data de modificação e hash SHA-256, evitando reler documentos inalterados.
- Consolidação local em JSON e CSV.

## Arquitetura

```text
PDFs locais
    │
    ▼
PyMuPDF — extração do texto por página
    │
    ▼
Normalização de rótulos e aliases EN / ES / PT
    │
    ▼
Segmentação de ordens e páginas de continuação
    │
    ▼
Parser de campos + listas de eventos + sinalizadores de qualidade
    │
    ▼
Controle incremental local (SHA-256)
    │
    ▼
JSON + CSV
```

O código não contém integração com provedores de nuvem, sistemas corporativos, bancos remotos ou APIs. Uma pasta sincronizada por uma ferramenta externa pode ser informada como diretório de entrada, mas a sincronização é responsabilidade do usuário e não é controlada pelo projeto.

## Estrutura do repositório

```text
local-work-order-pdf-extractor/
├── .github/workflows/tests.yml
├── data/input/.gitkeep
├── docs/ARCHITECTURE.md
├── scripts/check_release.py
├── src/
│   ├── __init__.py
│   └── work_order_extractor.py
├── tests/test_parser.py
├── .env.example
├── .gitignore
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── requirements.txt
├── SECURITY.md
└── README.md
```

## Instalação no Windows

Requisitos: Python 3.10 ou superior.

Abra o PowerShell na pasta do projeto:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Para utilizar as variáveis de ambiente opcionais:

```powershell
Copy-Item .env.example .env
```

O arquivo `.env` não deve ser versionado. Por padrão, o extrator procura PDFs em `data/input` e grava os resultados em `output`.

## Execução

Coloque localmente os PDFs que deseja processar em `data/input` (esta pasta é ignorada pelo Git) e execute:

```powershell
python -m src.work_order_extractor
```

Também é possível informar pastas explicitamente:

```powershell
python -m src.work_order_extractor --input-dir "C:\caminho\para\pdfs" --output-dir "output"
```

Para incluir subpastas:

```powershell
python -m src.work_order_extractor --recursive
```

Para reprocessar todos os documentos, ignorando o controle incremental:

```powershell
python -m src.work_order_extractor --force
```

Para testar um único PDF:

```powershell
python -m src.work_order_extractor --test-pdf "C:\caminho\para\exemplo.pdf" --output-dir "output_teste"
```

## Saídas

| Arquivo | Descrição |
|---|---|
| `ordens_servico.json` | Registros hierárquicos com campos extraídos, listas, texto bruto e sinalizadores de qualidade. |
| `ordens_servico.csv` | Uma linha por ordem. Estruturas aninhadas são serializadas como JSON nas células. |
| `controle_processamento.json` | Estado incremental local, assinaturas e hashes usados para detectar inclusões, alterações e remoções. |

As datas de origem são mantidas como texto quando o formato pode ser ambíguo entre localidades. Durações negativas, quando presentes na fonte, são preservadas e marcadas para revisão. Campos ausentes permanecem vazios ou `null`; o parser não tenta preencher valores por inferência.

**Privacidade dos caminhos:** os registros exportados guardam somente o nome do arquivo de origem, não o caminho absoluto do computador. As chaves do controle incremental são relativas à pasta de entrada. Ainda assim, os arquivos de saída podem conter dados operacionais e devem permanecer fora de repositórios públicos.

## Testes e verificação

```powershell
python -m unittest discover -s tests -v
python scripts/check_release.py
```

A suíte utiliza texto e PDFs sintéticos gerados em diretório temporário durante a execução. Não depende de documentos reais, caminhos pessoais ou acesso a sistemas externos. O workflow de GitHub Actions executa os testes automaticamente em cada push e pull request.

## Limitações conhecidas

- Layouts novos ou muito diferentes podem exigir novos aliases e testes unitários.
- PDFs digitalizados como imagem podem não conter texto selecionável. OCR não está incluído nesta versão.
- Tabelas com células mescladas ou descrições quebradas entre páginas são preservadas como linhas textuais; a associação rigorosa de todas as colunas requer extração geométrica e validação visual.
- O reconhecimento multilíngue cobre os aliases definidos no código, não todos os idiomas ou modelos de formulário existentes.
- Uma execução bem-sucedida não substitui a validação humana dos campos críticos antes de qualquer uso operacional.

## Privacidade e uso responsável

- Não publique PDFs, capturas de tela, dados exportados, logs, arquivos de controle incremental ou configurações locais.
- Não use dados pessoais, identificadores internos, nomes de clientes, fornecedores, instalações ou ativos nos exemplos do repositório.
- Mantenha `.env`, `data/`, `output/` e arquivos de teste reais fora do Git.
- Antes de publicar alterações, execute `python scripts/check_release.py` e revise manualmente a lista de arquivos staged com `git status` e `git diff --cached`.
- O processamento local reduz a exposição a serviços externos, mas não substitui as políticas de segurança, classificação da informação e autorização da organização proprietária dos documentos.

## English summary

A local-first Python utility that extracts structured data from work-order PDFs. It supports configurable English, Spanish and Portuguese labels, multi-page record grouping, incremental processing, JSON/CSV export and data-quality flags. Tests use synthetic fixtures only. No production documents, corporate data or external service integrations are included.

This repository is a generic portfolio demonstration. It is not affiliated with or endorsed by any document issuer, employer, customer or supplier.
