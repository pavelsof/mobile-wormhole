import hashlib
import json
import os

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, TimeoutError
from twisted.protocols.basic import FileSender
from wormhole import create
from wormhole.cli.cmd_send import APPID
from wormhole.cli.public_relay import RENDEZVOUS_RELAY, TRANSIT_RELAY
from wormhole.errors import WrongPasswordError
from wormhole.transit import TransitReceiver, TransitSender


class HumanError(Exception):
    """
    Raised when one of the humans at either end of the wormhole does something
    that breaks it, e.g. enters the wrong code.
    """
    pass


class SuspiciousOperation(Exception):
    """
    Raised when things do not go according to the protocol, e.g. a message that
    cannot be parsed is received.
    """
    pass


class Timeout(Exception):
    """
    Raised when the rendezvous server or the other end of the wormhole take
    longer than expected to respond.
    """
    pass


class TransferError(Exception):
    """
    Raised when the file transfer failed, e.g. the connection drops before all
    the bytes have been transferred.
    """
    pass


class Wormhole:
    """
    Wrapper around magic wormhole's code that makes it easier to reason about
    what is going on, at least for me. Usage for sending files:

        wormhole = Wormhole()
        code = yield wormhole.generate_code()
        verifier = yield wormhole.exchange_keys()
        hex_digest = yield wormhole.send_file(file_path)

    Usage for receiving files:

        wormhole = Wormhole()
        code = yield wormhole.connect(code)
        verifier = yield wormhole.exchange_keys()
        offer = yield wormhole.await_offer()
        hex_digest = yield wormhole.accept_offer(file_path)

    Almost all methods return Deferred instances that either resolve into the
    respective value (e.g. the generated code) or reject with one of the four
    errors defined above.
    """

    def __init__(
            self, app_id=APPID, rendezvous_relay=RENDEZVOUS_RELAY,
            transit_relay=TRANSIT_RELAY
        ):
        """
        Create a magic wormhole.
        """
        self.app_id = app_id
        self.rendezvous_relay = rendezvous_relay
        self.transit_relay = transit_relay

        self.wormhole = create(self.app_id, self.rendezvous_relay, reactor)

        self.offer = None
        self.transit = None

    @inlineCallbacks
    def generate_code(self, timeout=10):
        """
        Generate the code that the users at the two ends of the wormhole will
        have to exchange.

        Return a Deferred that resolves into the code.
        """
        self.wormhole.allocate_code()

        deferred = self.wormhole.get_code()
        deferred.addTimeout(timeout, reactor)

        try:
            code = yield deferred
        except TimeoutError:
            raise Timeout('could not connect to the server')

        return returnValue(code)

    @inlineCallbacks
    def connect(self, code, timeout=10):
        """
        Connect to another wormhole client by its code generated. This has to
        be exchanged between the two users before the wormhole connects.

        Return a Deferred that resolves upon successful connection.
        """
        self.wormhole.set_code(code)

        deferred = self.wormhole.get_code()
        deferred.addTimeout(timeout, reactor)

        try:
            code = yield deferred
        except TimeoutError:
            raise Timeout('could not connect to the other end')

        return returnValue(code)

    @inlineCallbacks
    def exchange_keys(self, timeout=10):
        """
        Return a Deferred that resolves when the key exchange between the two
        clients has been completed.

        The Deferred resolves into the so-called verifier, a hash of the shared
        key, which can be compared by the users at both ends of the wormhole in
        order to make sure no man-in-the-middle attack is taking place.
        """
        deferred = self.wormhole.get_verifier()
        deferred.addTimeout(timeout, reactor)

        try:
            verifier = yield deferred
        except TimeoutError:
            raise Timeout('could not exchange keys with the other end')
        except WrongPasswordError:
            raise HumanError('the other end entered a wrong code')

        return returnValue(verifier)

    def send_json(self, message):
        """
        Send a JSON message down the wormhole.
        """
        self.wormhole.send_message(bytes(json.dumps(message), 'utf-8'))

    @inlineCallbacks
    def await_json(self, timeout=600):
        """
        Return a Deferred that resolves into the next JSON message that comes
        out of the wormhole.
        """
        deferred = self.wormhole.get_message()
        deferred.addTimeout(timeout, reactor)

        try:
            message = yield deferred
            message = json.loads(str(message, 'utf-8'))
        except TimeoutError:
            raise Timeout('no message came from the other side')
        except:
            raise SuspiciousOperation('bad message came from the other side')

        return returnValue(message)

    @inlineCallbacks
    def send_file(self, file_path):
        """
        Send a file down the wormhole. As per the file-transfer protocol this
        involves the following steps:

        - send a message with the details needed for establishing the transit;
        - send a message with the offer, i.e. the name and size of the file;
        - run a loop waiting for the response(s) of the other end.

        Return a Deferred that resolves when the file has been transferred.
        """
        assert self.transit is None and os.path.exists(file_path)

        self.transit = TransitSender(self.transit_relay)
        our_hints = yield self.transit.get_connection_hints()
        our_abilities = self.transit.get_connection_abilities()

        self.send_json({
            'transit': {
                'abilities-v1': our_abilities,
                'hints-v1': our_hints,
            }
        })

        self.send_json({
            'offer': {
                'file': {
                    'filename': os.path.basename(file_path),
                    'filesize': os.stat(file_path).st_size
                }
            }
        })

        while True:
            message = yield self.await_json()

            if 'error' in message:
                yield self.close()
                raise SuspiciousOperation(str(message['error']))

            if 'transit' in message:
                self.transit.add_connection_hints(
                    message['transit']['hints-v1']
                )

                transit_key = self.wormhole.derive_key(
                    '{}/transit-key'.format(self.app_id),
                    self.transit.TRANSIT_KEY_LENGTH
                )
                self.transit.set_transit_key(transit_key)

            if 'answer' in message:
                try:
                    assert message['answer']['file_ack'] == 'ok'
                except (AssertionError, KeyError):
                    raise HumanError('the other side declined the file')
                else:
                    hex_digest = yield self.transfer_file(file_path)
                    return returnValue(hex_digest)

    @inlineCallbacks
    def transfer_file(self, file_path):
        """
        Send a file via the transit. Assume that the latter has been already
        established. If the other end provides a hash when done, check it.

        Helper for the send_file method above.
        """
        record_pipe = yield self.transit.connect()
        hasher = hashlib.sha256()

        def func(data):
            hasher.update(data)
            return data

        with open(file_path, 'rb') as f:
            file_sender = FileSender()
            yield file_sender.beginFileTransfer(f, record_pipe, func)

        ack_record = yield record_pipe.receive_record()
        ack_record = json.loads(str(ack_record, 'utf-8'))

        yield record_pipe.close()

        try:
            assert ack_record['ack'] == 'ok'
            if ack_record['sha256']:
                assert ack_record['sha256'] == hasher.hexdigest()
        except (AssertionError, KeyError):
            raise TransferError('file transfer failed')

        return returnValue(hasher.hexdigest())

    @inlineCallbacks
    def await_offer(self):
        """
        Start waiting for the other end of the wormhole to send a file offer.

        As per the file-transfer protocol this involves running a loop waiting
        for both transit details and the offer itself. The transit should be
        already established when the incoming file offer is processed.

        Return a Deferred that resolves into a {filename, filesize} dict.
        """
        assert self.transit is None

        self.transit = TransitReceiver(self.transit_relay)

        transit_key = self.wormhole.derive_key(
            '{}/transit-key'.format(self.app_id),
            self.transit.TRANSIT_KEY_LENGTH
        )
        self.transit.set_transit_key(transit_key)

        while True:
            message = yield self.await_json()

            if 'error' in message:
                yield self.close()
                raise SuspiciousOperation(str(message['error']))

            if 'transit' in message:
                self.transit.add_connection_hints(
                    message['transit']['hints-v1']
                )
                our_hints = yield self.transit.get_connection_hints()
                our_abilities = self.transit.get_connection_abilities()

                self.send_json({
                    'transit': {
                        'abilities-v1': our_abilities,
                        'hints-v1': our_hints,
                    }
                })

            if 'offer' in message:
                self.offer = message['offer']
                return returnValue(self.offer['file'])

    @inlineCallbacks
    def accept_offer(self, file_path):
        """
        Download the file sent by the other end and write it to the specified
        location. Assume that the transit has been already established.

        Return a Deferred that resolves into the hex digest of the transferred
        data once the download is completed.
        """
        assert self.offer and self.transit

        size = self.offer['file']['filesize']
        self.offer = None

        self.send_json({'answer': {'file_ack': 'ok'}})

        record_pipe = yield self.transit.connect()
        hasher = hashlib.sha256()

        with open(file_path, 'wb') as f:
            received = yield record_pipe.writeToFile(
                f, size, progress=None, hasher=hasher.update
            )

            if received != size:
                raise TransferError('download did not complete')

        ack_record = {'ack': 'ok', 'sha256': hasher.hexdigest()}
        ack_record = bytes(json.dumps(ack_record), 'utf-8')
        yield record_pipe.send_record(ack_record)

        yield record_pipe.close()

        return returnValue(hasher.hexdigest())

    def close(self):
        """
        Close the wormhole.

        Return a Deferred that resolves into the string "happy" when done or
        rejects with one of the following errors: WelcomeError, ServerError,
        LonelyError, WrongPasswordError [1].

        [1]: https://magic-wormhole.readthedocs.io/en/latest/api.html#closing
        """
        deferred = self.wormhole.close()
        return deferred
