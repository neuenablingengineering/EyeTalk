import atexit
import os
import subprocess as sp
import numpy as np
from time import sleep
from keras.layers import Dense
from keras.models import Sequential
from keras.optimizers import SGD
from keras.utils.np_utils import to_categorical
from keras.callbacks import Callback

from backend.ipc_reader import IPCReader


class GazeDetector:
    LEFT_EYE = 0
    RIGHT_EYE = 1

    def __init__(self, external_camera=False):

        # TODO: parameterize so that we can pass in the camera number
        self.cpp_proc = sp.Popen(['{prefix}/backend/eyefinder_cpp/build/eyefinder'.format(prefix=os.getcwd())])

        # clean up IPC at end
        atexit.register(self.cleanup)
        sleep(2)
        self.active = (self.cpp_proc.poll() is not None)

        self.neural_network = None
        self.init_model()

        self.last_id_seen = -1
        self.last_probabilities = None

        self.training_epochs = 0
        self.current_epoch = 0

    def init_model(self):
        model = Sequential()
        model.add(Dense(20, input_shape=(4,), kernel_initializer='uniform', activation='relu'))
        model.add(Dense(20, kernel_initializer='uniform', activation='relu'))
        model.add(Dense(11, activation="softmax"))
        model.compile(loss='categorical_crossentropy', optimizer=SGD(lr=0.025))
        self.neural_network = model

    def sample(self):
        """
        Read an image from the video capture device and determine where the user is looking
        :return: a ndarray of probabilities for each label in the UI
        """

        features = self.sample_features()

        feature_id = features[0]

        if feature_id != self.last_id_seen:

            self.last_id_seen = feature_id

            used_features = self.extract_used_features(features)
            probabilities = self.calculate_location_probabilities_from_features(used_features)
            self.last_probabilities = probabilities

        else:
            probabilities = self.last_probabilities

        return feature_id, probabilities

    def cleanup(self):
        """
        Clean up the semaphore, shared memory, and kill the eye finder process
        """
        with IPCReader() as reader:
            reader.clean()
        self.cpp_proc.kill()

    @staticmethod
    def sample_features():
        """
        Read an image from the video capture device and return the extracted features of the image
        :return: a ndarray of shape(30) full of numerical features
        """
        with IPCReader() as reader:
            return np.asarray(reader.read())

    def extract_used_features(self, vector):
        return vector[25:29]

    def calculate_location_probabilities_from_features(self, features):
        """
        Feed features through a machine learning algorithm to get probabilities
        :param features: a ndarray of shape(30) full of numerical features
        :return: a ndarray of probabilities for each label in the UI
        """

        features = np.asarray([features, ])

        prediction_vals = self.neural_network.predict(features)
        return prediction_vals

    def train_location_classifier(self, data, labels, num_epochs=750):
        """
        Train location classifier using data
        :param data: a ndarray of shape(N, 30) of N rows of numerical features
        :param num_epochs: an integer number for how many iterations through all the data the training will do
        """

        np_data = np.asarray(data)
        categorical_labels = to_categorical(labels)

        self.training_epochs = num_epochs

        callback = ProgressCallback(self)

        self.neural_network.fit(np_data, categorical_labels, epochs=num_epochs, callbacks=[callback])

    def test_accuracy(self, data, labels):
        """
        Print out the accuracy of the predictions on a given set of data and labels
        :param data: a list of np arrays
        :param labels: a list of integers labels in the range [0, 10]
        """

        total = 0
        count = 0

        for i in range(len(data)):
            test_data = data[i]
            test_label = labels[i]
            probabilities = self.calculate_location_probabilities_from_features(test_data)
            predicted_label = np.argmax(probabilities)
            count += int(predicted_label == test_label)
            total += 1

        # print(count, total)
        percent = count * 1.0 / total

        print('Percent correct:', percent)


class ProgressCallback(Callback):
    def __init__(self, detector):
        Callback.__init__(self)
        self.detector = detector

    def on_epoch_end(self, epoch, logs=None):
        self.detector.current_epoch = epoch


if __name__ == '__main__':
    tracker = GazeDetector()
    sleep(1)
    for _ in range(100):
        sleep(0.05)
        tracker.sample()
