# Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
# Copyright 2015 and onwards Google, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from nemo_text_processing.text_normalization.en.graph_utils import GraphFst, delete_extra_space, delete_space
from nemo_text_processing.text_normalization.en.taggers.punctuation import PunctuationFst
from nemo_text_processing.text_normalization.en.taggers.word import WordFst
from nemo_text_processing.text_normalization.ru.taggers.cardinal import CardinalFst
from nemo_text_processing.text_normalization.ru.taggers.date import DateFst
from nemo_text_processing.text_normalization.ru.taggers.decimals import DecimalFst
from nemo_text_processing.text_normalization.ru.taggers.electronic import ElectronicFst
from nemo_text_processing.text_normalization.ru.taggers.measure import MeasureFst
from nemo_text_processing.text_normalization.ru.taggers.money import MoneyFst
from nemo_text_processing.text_normalization.ru.taggers.number_names import get_alternative_formats, get_number_names
from nemo_text_processing.text_normalization.ru.taggers.ordinal import OrdinalFst
from nemo_text_processing.text_normalization.ru.taggers.telephone import TelephoneFst
from nemo_text_processing.text_normalization.ru.taggers.time import TimeFst
from nemo_text_processing.text_normalization.ru.taggers.whitelist import WhiteListFst

try:
    import pynini
    from pynini.lib import pynutil

    PYNINI_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    PYNINI_AVAILABLE = False


class ClassifyFst(GraphFst):
    """
    Final class that composes all other classification grammars. This class can process an entire sentence, that is lower cased.
    For deployment, this grammar will be compiled and exported to OpenFst Finate State Archiv (FAR) File. 
    More details to deployment at NeMo/tools/text_processing_deployment.

    Args:
        input_case: accepting either "lower_cased" or "cased" input.
        deterministic: if True will provide a single transduction option,
            for False multiple options (used for audio-based normalization)
    """

    def __init__(self, input_case: str, deterministic: bool = True):
        super().__init__(name="tokenize_and_classify", kind="classify", deterministic=deterministic)
        print('Ru TN only supports non-deterministic cases and produces multiple normalization options.')

        number_names = get_number_names()
        alternative_formats = get_alternative_formats()

        self.cardinal = CardinalFst(
            number_names=number_names, alternative_formats=alternative_formats, deterministic=deterministic
        )
        cardinal_graph = self.cardinal.fst

        self.ordinal = OrdinalFst(
            number_names=number_names, alternative_formats=alternative_formats, deterministic=deterministic
        )
        ordinal_graph = self.ordinal.fst

        self.decimal = DecimalFst(cardinal=self.cardinal, ordinal=self.ordinal, deterministic=deterministic)
        decimal_graph = self.decimal.fst

        self.measure = MeasureFst(cardinal=self.cardinal, decimal=self.decimal, deterministic=deterministic)
        measure_graph = self.measure.fst
        self.date = DateFst(number_names=number_names, deterministic=deterministic)
        date_graph = self.date.fst
        word_graph = WordFst(deterministic=deterministic).fst
        self.time = TimeFst(number_names=number_names, deterministic=deterministic)
        time_graph = self.time.fst
        self.telephone = TelephoneFst(number_names=number_names, deterministic=deterministic)
        telephone_graph = self.telephone.fst
        self.electronic = ElectronicFst(deterministic=deterministic)
        electronic_graph = self.electronic.fst
        self.money = MoneyFst(cardinal=self.cardinal, decimal=self.decimal, deterministic=deterministic)
        money_graph = self.money.fst
        self.whitelist = WhiteListFst(input_case=input_case, deterministic=deterministic)
        whitelist_graph = self.whitelist.fst
        punct_graph = PunctuationFst(deterministic=deterministic).fst

        classify = (
            pynutil.add_weight(whitelist_graph, 1.01)
            | pynutil.add_weight(time_graph, 1.1)
            | pynutil.add_weight(date_graph, 1.09)
            | pynutil.add_weight(decimal_graph, 1.1)
            | pynutil.add_weight(measure_graph, 0.9)
            | pynutil.add_weight(cardinal_graph, 1.1)
            | pynutil.add_weight(ordinal_graph, 1.1)
            | pynutil.add_weight(money_graph, 1.1)
            | pynutil.add_weight(telephone_graph, 1.1)
            | pynutil.add_weight(electronic_graph, 1.1)
            | pynutil.add_weight(word_graph, 100)
        )

        punct = pynutil.insert("tokens { ") + pynutil.add_weight(punct_graph, weight=1.1) + pynutil.insert(" }")
        token = pynutil.insert("tokens { ") + classify + pynutil.insert(" }")
        token_plus_punct = (
            pynini.closure(punct + pynutil.insert(" ")) + token + pynini.closure(pynutil.insert(" ") + punct)
        )

        graph = token_plus_punct + pynini.closure(pynutil.add_weight(delete_extra_space, 1.1) + token_plus_punct)
        graph = delete_space + graph + delete_space

        self.fst = graph.optimize()