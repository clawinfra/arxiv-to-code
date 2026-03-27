"""Shared test fixtures for arxiv-to-code tests."""

import pytest
from datetime import datetime, timezone, timedelta

from arxiv_to_code.scanner import Paper


@pytest.fixture
def fresh_paper():
    """A paper submitted 12 hours ago with no code."""
    return Paper(
        arxiv_id="2403.12345",
        title="A Novel Framework for Secure Multi-Party Computation with Differential Privacy",
        abstract=(
            "We propose a novel framework that combines secure multi-party computation "
            "with differential privacy guarantees. Our algorithm achieves sub-linear "
            "communication complexity while maintaining strong privacy bounds. "
            "We present a detailed protocol and prove its security under standard "
            "cryptographic assumptions. Step 1 involves key generation, step 2 "
            "performs the secure aggregation."
        ),
        authors=["Alice Smith", "Bob Jones", "Carol Lee"],
        categories=["cs.CR", "cs.AI"],
        submitted=datetime.now(timezone.utc) - timedelta(hours=12),
        pdf_url="https://arxiv.org/pdf/2403.12345",
    )


@pytest.fixture
def stale_paper():
    """A paper submitted 72 hours ago."""
    return Paper(
        arxiv_id="2403.00001",
        title="Revisiting Transformer Architectures for Image Classification",
        abstract=(
            "We revisit the design of transformer architectures for image classification. "
            "We find that simple modifications to the attention mechanism yield significant "
            "improvements on standard benchmarks."
        ),
        authors=["Dave Wilson"],
        categories=["cs.LG"],
        submitted=datetime.now(timezone.utc) - timedelta(hours=72),
        pdf_url="https://arxiv.org/pdf/2403.00001",
    )


@pytest.fixture
def paper_with_code():
    """A paper that mentions code availability."""
    return Paper(
        arxiv_id="2403.99999",
        title="FastDiff: Accelerated Diffusion Models",
        abstract=(
            "We present FastDiff, a method for accelerating diffusion model inference. "
            "Our code is available at github.com/example/fastdiff. "
            "We release all models and training scripts."
        ),
        authors=["Eve Brown"],
        categories=["cs.LG", "cs.AI"],
        submitted=datetime.now(timezone.utc) - timedelta(hours=6),
        pdf_url="https://arxiv.org/pdf/2403.99999",
    )


@pytest.fixture
def sample_arxiv_xml():
    """Sample arXiv API XML response."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title>ArXiv Query</title>
  <opensearch:totalResults>2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2403.12345v1</id>
    <title>A Novel Framework for Secure Computation</title>
    <summary>We propose a novel algorithm for secure computation with provable guarantees.</summary>
    <published>{now}</published>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <arxiv:primary_category term="cs.CR" />
    <category term="cs.CR" />
    <category term="cs.AI" />
    <link href="http://arxiv.org/pdf/2403.12345v1" type="application/pdf" />
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2403.00002v1</id>
    <title>Improving Language Models with Retrieval</title>
    <summary>We introduce a method for improving language model performance. We release our code and models.</summary>
    <published>{old}</published>
    <author><name>Carol Lee</name></author>
    <category term="cs.LG" />
    <link href="http://arxiv.org/pdf/2403.00002v1" type="application/pdf" />
  </entry>
</feed>""".format(
        now=(datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        old=(datetime.now(timezone.utc) - timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
